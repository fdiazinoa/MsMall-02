import json
from decimal import Decimal

import pytest
from services.calculated_fields_service import calculated_fields


def formula(operator='+', decimal='.'):
    return {'_total_bruto_mode': 'calculated', '_total_bruto_calc_left': 'Neto',
            '_total_bruto_calc_right': 'Impuesto', '_total_bruto_calc_operator': operator,
            '_decimal_separator': decimal}


@pytest.mark.parametrize('operator,expected', [('+','12'),('-','8'),('*','20'),('/','5')])
def test_arithmetic_uses_source_columns(operator, expected):
    assert calculated_fields({'Neto':'10','Impuesto':'2'}, formula(operator))['total_bruto'] == expected


def test_locale_zero_negative_and_native_json_numbers():
    assert calculated_fields({'neto':'1.000,50','IMPUESTO':'180,09'}, formula(decimal=','))['total_bruto'] == '1180,59'
    assert calculated_fields({'Neto':'0','Impuesto':'2'}, formula('-'))['total_bruto'] == '-2'
    assert calculated_fields({'Neto':10.5,'Impuesto':1.5}, formula(decimal=','))['total_bruto'] == '12,0'
    assert calculated_fields({'Neto':'0.1','Impuesto':'0.2'}, formula())['total_bruto'] == '0.3'


@pytest.mark.parametrize('row,config,reason', [
    ({'Neto':'10','Impuesto':'0'},formula('/'),'División entre cero'),
    ({'Neto':'abc','Impuesto':'2'},formula(),'Valor no numérico'),
    ({'Neto':'NaN','Impuesto':'2'},formula(),'Valor no numérico'),
    ({'Neto':'','Impuesto':'2'},formula(),'Valor no numérico'),
    ({'Neto':'10'},formula(),'Columna de cálculo no encontrada'),
    ({'Neto':'10','Impuesto':'2'},formula('**'),'Operación no permitida'),
])
def test_invalid_calculation_is_an_explicit_error(row, config, reason):
    with pytest.raises(ValueError, match=reason): calculated_fields(row, config)


def test_legacy_mapping_has_no_calculations():
    assert calculated_fields({'Neto':'bad'}, {}) == {}


@pytest.mark.parametrize('kind', ['CSV','JSON'])
@pytest.mark.parametrize('decimal', ['.',','])
def test_manual_and_worker_calculations_match(monkeypatch, kind, decimal):
    from test_sales_local_validation import _load_main, _FakeSupabase
    from test_worker_auto_import_confirmation import _FakeWorkerSupabase
    import worker_importacion as worker
    main = _load_main(monkeypatch)
    db = _FakeSupabase({'locales':[{'id':'local-1','codigo_interno':'L001','mall_id':'mall-1'}], 'ventas':[]})
    worker_db = _FakeWorkerSupabase()
    monkeypatch.setattr(main, 'supabase', db)
    monkeypatch.setattr(worker, 'supabase', worker_db)
    mapping = {'factura_numero':'Factura','fecha_venta':'Fecha','local_codigo':'Local','total_neto':'Neto','total_impuestos':'Impuesto'}
    constants = formula(decimal=decimal)
    row = {'Factura':'001','Fecha':'2026-11-25','Local':'L001','Neto':'100','Impuesto':'18'}
    if kind == 'JSON': content = json.dumps([row])
    else: content = 'Factura;Fecha;Local;Neto;Impuesto\n001;2026-11-25;L001;100;18\n'
    count, errors = main.process_file_content(content, 'ventas.'+kind.lower(), {'tipo_archivo':kind,'mapping':mapping,'constants':constants}, 'test', 'mall-1')
    assert count == 1 and errors == [], errors
    count, errors, _ = worker.process_file_logic({'id':'local-1','nombre':'Local','mall_id':'mall-1','file_type':kind,'mapping_config':mapping,'constants_config':constants}, 'ventas.'+kind.lower(), content)
    assert count == 1 and errors == [], errors
    assert db.upserts[0]['total_bruto'] == worker_db.tables['ventas'][0]['total_bruto'] == 118.0


def test_both_importers_report_division_by_zero_without_writes(monkeypatch):
    from test_sales_local_validation import _load_main, _FakeSupabase
    from test_worker_auto_import_confirmation import _FakeWorkerSupabase
    import worker_importacion as worker
    main = _load_main(monkeypatch)
    db = _FakeSupabase({'locales':[], 'ventas':[]})
    worker_db = _FakeWorkerSupabase()
    monkeypatch.setattr(main, 'supabase', db)
    monkeypatch.setattr(worker, 'supabase', worker_db)
    mapping = {'factura_numero':'Factura','fecha_venta':'Fecha','local_codigo':'Local'}
    constants = formula('/')
    content = 'Factura;Fecha;Local;Neto;Impuesto\n001;2026-11-25;L001;100;0\n'
    manual = main.process_file_content(content, 'ventas.csv', {'tipo_archivo':'CSV','mapping':mapping,'constants':constants}, 'test', 'mall-1')
    automatic = worker.process_file_logic({'id':'local-1','nombre':'Local','mall_id':'mall-1','mapping_config':mapping,'constants_config':constants}, 'ventas.csv', content)
    for result in (manual, automatic):
        assert result[0] == 0
        assert result[1][0]['linea'] == 2
        assert 'División entre cero' in result[1][0]['error']
    assert not db.upserts and not worker_db.tables.get('ventas')
