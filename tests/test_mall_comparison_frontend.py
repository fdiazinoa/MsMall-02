from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_comparison_workspace_preserves_period_view_and_adds_cross_mall_view():
    dashboard = (ROOT / 'components' / 'Dashboard.tsx').read_text()
    workspace = (ROOT / 'components' / 'ComparisonsWorkspace.tsx').read_text()
    sidebar = (ROOT / 'components' / 'Sidebar.tsx').read_text()

    assert 'ComparisonsWorkspace' in dashboard
    assert '<MallComparison />' in workspace
    assert '<PeriodComparison />' in workspace
    assert 'Comparativa Malls' in sidebar
    assert "canAccess('comparisons')" in sidebar


def test_cross_mall_view_has_required_dimensions_and_authenticated_api_call():
    component = (ROOT / 'components' / 'MallComparison.tsx').read_text()
    api = (ROOT / 'api.ts').read_text()

    for dimension in ('malls', 'locales', 'rubros', 'categorias'):
        assert f"id: '{dimension}'" in component
    assert 'getMallComparison' in component
    assert "params.append('mall_ids', mallId)" in api
    assert "headers: withAuthHeaders(token)" in api
    assert 'AbortController' in component
