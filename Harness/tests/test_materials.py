import pytest
from printlab import bambuddy, core

BASELINE={'confirmed_at':'2026-10-25','initial_snapshot':[{'spool_id':1,'label_weight':1000,'weight_used':0}]}


def test_initial_full_confirmation_never_freezes_future_remaining():
    row={'id':1,'label_weight':1000,'weight_used':0}
    first=bambuddy.material_quantity(row,BASELINE)
    assert first['remaining_percent']==100 and first['quantity_basis']=='inventory_estimate'
    assert first['actual_remaining_percent'] is None and first['historical_baseline']['remaining_percent']==100
    used=bambuddy.material_quantity({**row,'weight_used':123.4},BASELINE)
    assert used['remaining_weight']==876.6 and used['remaining_percent']==87.66
    assert used['quantity_basis']=='inventory_estimate' and used['measured'] is False
    assert bambuddy.material_quantity({**row,'id':2},BASELINE)['quantity_basis']=='inventory_estimate'


@pytest.mark.parametrize('label,used',[(0,0),(None,0),(1000,None),(1000,-1),(1000,float('nan')),(True,0)])
def test_unknown_or_invalid_data_is_never_assumed_full(label,used):
    row=bambuddy.material_quantity({'id':1,'label_weight':label,'weight_used':used},BASELINE)
    assert row['remaining_percent'] is None and row['quantity_basis']=='unknown'


def test_inventory_and_cold_context_read_current_shared_quantities(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'ROOT',tmp_path)
    core.write_json(tmp_path/'Library/Materials/quantity-baseline-2026-10-25.json',BASELINE)
    rows=[{'id':1,'label_weight':1000,'weight_used':0,'tag_uid':'private-tag'}]
    class Fake:
        def get(self,path):
            assert path=='inventory/spools'
            return rows
        def close(self): pass
    monkeypatch.setattr(bambuddy,'Client',Fake)
    assert core.context()['materials']['items'][0]['remaining_percent']==100
    rows[0]['weight_used']=25
    current=core.context()['materials']['items'][0]
    assert current['remaining_percent']==97.5 and 'tag_uid' not in current
    assert rows[0]['weight_used']==25  # Reading never deducts the print again.
