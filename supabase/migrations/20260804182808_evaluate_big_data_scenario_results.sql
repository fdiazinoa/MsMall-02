-- Big Data Phase 3B: automatically compare finished scenarios with observed sales.
-- The function is intentionally SECURITY INVOKER and callable only by service_role.

begin;

alter table public.big_data_scenarios
    add column if not exists evaluation jsonb,
    add column if not exists evaluated_at timestamptz;

alter table public.big_data_scenarios
    drop constraint if exists big_data_scenarios_evaluation_object_ck;

alter table public.big_data_scenarios
    add constraint big_data_scenarios_evaluation_object_ck
    check (evaluation is null or jsonb_typeof(evaluation) = 'object');

create index if not exists big_data_scenarios_pending_evaluation_idx
    on public.big_data_scenarios (mall_id, end_date)
    where status in ('ACTIVE', 'COMPLETED');

comment on column public.big_data_scenarios.evaluation is
    'Observed net-sales comparison calculated after an active/completed scenario period ends. It measures forecast fit and does not prove causality.';
comment on column public.big_data_scenarios.evaluated_at is
    'Timestamp of the latest material scenario evaluation refresh.';

create or replace function public.refresh_big_data_scenario_results(
    p_mall_id uuid,
    p_as_of date
)
returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    refreshed_count integer := 0;
begin
    if p_mall_id is null or p_as_of is null then
        raise exception 'mall_id and as_of are required';
    end if;

    with eligible as (
        select
            scenario.id,
            scenario.start_date,
            scenario.end_date,
            scenario.baseline_sales,
            scenario.scenario_sales,
            scenario.lower_bound,
            scenario.upper_bound
        from public.big_data_scenarios as scenario
        where scenario.mall_id = p_mall_id
          and scenario.status in ('ACTIVE', 'COMPLETED')
          and scenario.end_date < p_as_of
    ),
    observed as (
        select
            eligible.id,
            eligible.start_date,
            eligible.end_date,
            eligible.baseline_sales,
            eligible.scenario_sales,
            eligible.lower_bound,
            eligible.upper_bound,
            sum(aggregate.sales_net) filter (
                where aggregate.period_date is not null
            ) as actual_sales,
            coalesce(sum(aggregate.transaction_count) filter (
                where aggregate.period_date is not null
            ), 0) as actual_transactions,
            count(aggregate.period_date)::integer as days_with_sales,
            (count(aggregate.period_date) filter (
                where aggregate.coverage_status = 'incomplete'
            ))::integer as incomplete_days,
            max(aggregate.updated_at) as data_updated_at
        from eligible
        left join public.big_data_daily_aggregates as aggregate
          on aggregate.mall_id = p_mall_id
         and aggregate.grain = 'mall'
         and aggregate.period_date between eligible.start_date and eligible.end_date
        group by
            eligible.id,
            eligible.start_date,
            eligible.end_date,
            eligible.baseline_sales,
            eligible.scenario_sales,
            eligible.lower_bound,
            eligible.upper_bound
    ),
    calculated as (
        select
            observed.id,
            jsonb_build_object(
                'status', case
                    when observed.days_with_sales = 0 then 'NO_DATA'
                    when observed.incomplete_days > 0 then 'INCOMPLETE_DATA'
                    else 'READY'
                end,
                'result_status', case
                    when observed.days_with_sales = 0
                      or observed.incomplete_days > 0 then null
                    when observed.actual_sales > observed.upper_bound then 'ABOVE_RANGE'
                    when observed.actual_sales < observed.lower_bound then 'BELOW_RANGE'
                    else 'WITHIN_RANGE'
                end,
                'actual_sales', case
                    when observed.days_with_sales = 0 then null
                    else round(observed.actual_sales, 2)
                end,
                'actual_transactions', observed.actual_transactions,
                'scenario_sales', observed.scenario_sales,
                'baseline_sales', observed.baseline_sales,
                'variance_to_scenario', case
                    when observed.days_with_sales = 0 then null
                    else round(observed.actual_sales - observed.scenario_sales, 2)
                end,
                'variance_to_scenario_percent', case
                    when observed.days_with_sales = 0
                      or observed.scenario_sales = 0 then null
                    else round(
                        ((observed.actual_sales - observed.scenario_sales)
                            / observed.scenario_sales) * 100,
                        2
                    )
                end,
                'attainment_percent', case
                    when observed.days_with_sales = 0
                      or observed.scenario_sales = 0 then null
                    else round(
                        (observed.actual_sales / observed.scenario_sales) * 100,
                        2
                    )
                end,
                'variance_to_baseline', case
                    when observed.days_with_sales = 0 then null
                    else round(observed.actual_sales - observed.baseline_sales, 2)
                end,
                'variance_to_baseline_percent', case
                    when observed.days_with_sales = 0
                      or observed.baseline_sales = 0 then null
                    else round(
                        ((observed.actual_sales - observed.baseline_sales)
                            / observed.baseline_sales) * 100,
                        2
                    )
                end,
                'within_expected_range', case
                    when observed.days_with_sales = 0
                      or observed.incomplete_days > 0 then null
                    else observed.actual_sales between observed.lower_bound and observed.upper_bound
                end,
                'lower_bound', observed.lower_bound,
                'upper_bound', observed.upper_bound,
                'expected_days', (observed.end_date - observed.start_date + 1),
                'days_with_sales', observed.days_with_sales,
                'days_with_sales_percent', round(
                    observed.days_with_sales::numeric
                    / nullif((observed.end_date - observed.start_date + 1), 0)
                    * 100,
                    2
                ),
                'incomplete_days', observed.incomplete_days,
                'data_updated_at', observed.data_updated_at,
                'evaluated_through', observed.end_date,
                'sales_basis', 'NET',
                'methodology_version', 'big-data-scenario-evaluation-v1',
                'causality_notice',
                    'El resultado compara ventas observadas con el escenario guardado; no demuestra que la actividad haya causado la variación.'
            ) as evaluation
        from observed
    )
    update public.big_data_scenarios as scenario
       set evaluation = calculated.evaluation,
           evaluated_at = now()
      from calculated
     where scenario.id = calculated.id
       and scenario.mall_id = p_mall_id
       and scenario.evaluation is distinct from calculated.evaluation;

    get diagnostics refreshed_count = row_count;
    return refreshed_count;
end;
$$;

revoke all on function public.refresh_big_data_scenario_results(uuid, date)
    from public, anon, authenticated;
grant execute on function public.refresh_big_data_scenario_results(uuid, date)
    to service_role;

commit;
