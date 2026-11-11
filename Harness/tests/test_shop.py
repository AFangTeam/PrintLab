"""Only temporary workspaces; no shopping or printer network calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from printlab import core, shop
from printlab.api import app


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    core.new_project('测试项目甲')
    core.new_project('测试项目乙')
    return tmp_path


def part(**extra):
    return {'id':'magnet','name':'测试磁铁','category':'磁铁','unit':'个','quantity':4,
            'specification':{'直径':'6 mm','厚度':'2 mm','等级':'N52'},'spec_verified':True,**extra}


def confirm(pid):
    return shop.confirm(pid, '测试用户明确决定制作', 'isolated test session', shop.load()['version'])


def sync(pid, rows):
    return shop.sync(pid, rows, shop.load()['version'], 'isolated requirement evidence')


def stock(key, existing, purchased):
    return shop.stock(key, existing, purchased, 'Synthetic stock evidence', shop.load()['version'])


def test_decision_gate_unknowns_and_no_print_permission(ledger):
    with pytest.raises(core.WorkflowError, match='explicit decision'):
        sync('P001', [part()])
    confirm('测试项目甲')
    assert shop.view()['projects']['P001']['parts_reviewed'] is False
    row=sync('P001', [part(quantity=None,specification={},spec_verified=False)])['items'][0]
    assert row['to_buy'] is None and row['existing'] is None and row['status']=='unverified'
    assert core.summary(core.project_path('P001'))['shop']['count']==1
    assert core.read_json(core.project_path('P001')/'project.json')['status']=='designing'
    assert not list(ledger.rglob('approval.json'))
    with pytest.raises(core.WorkflowError, match='specification'):
        stock(row['id'],0,10)


def test_merge_idempotency_and_exact_spec_boundaries(ledger):
    confirm('P001'); confirm('P002')
    sync('P001',[part()]); sync('P001',[part()])
    result=sync('P002',[part(name='同规格不同名称',quantity=6)])
    assert len(result['items'])==1
    row=result['items'][0]
    assert row['required']==10 and len(row['sources'])==2
    assert shop.view('测试项目甲')['items'][0]['required']==10
    changed=sync('P002',[part(quantity=6,specification={'直径':'8 mm','厚度':'2 mm','等级':'N52'})])
    assert len(changed['items'])==2
    sync('P001',[part(spec_verified=False)]);sync('P002',[part(spec_verified=False)])
    assert len(shop.view()['items'])==2


def test_stock_states_and_consumption_cannot_double_count(ledger):
    confirm('P001');confirm('P002');sync('P001',[part()])
    row=sync('P002',[part(quantity=6)])['items'][0];key=row['id']
    assert stock(key,None,0)['items'][0]['status']=='unverified'
    row=stock(key,2,3)['items'][0];assert row['status']=='needed' and row['to_buy']==5
    assert stock(key,10,0)['items'][0]['status']=='owned'
    assert stock(key,2,8)['items'][0]['status']=='purchased'
    # Absolute stock values repeated in a later session never add another order.
    assert stock(key,2,8)['items'][0]['purchased']==8
    shop.fulfill('P001','Test: received and physically used',shop.load()['version'])
    row=shop.view()['items'][0]
    assert row['required']==6 and row['purchased']==6 and row['existing']==0 and row['to_buy']==0
    with pytest.raises(core.WorkflowError,match='already consumed'):
        shop.fulfill('P001','duplicate',shop.load()['version'])
    with pytest.raises(core.WorkflowError,match='new batch'):
        sync('P001',[part()])


def test_cancel_preserves_purchased_leftovers(ledger):
    confirm('P001');row=sync('P001',[part()])['items'][0]
    stock(row['id'],0,5)
    row=sync('P001',[])['items'][0]
    assert row['status']=='settled' and row['purchased']==5 and row['required']==0
    assert shop.view()['projects']['P001']['parts_reviewed'] is True


def test_mutations_are_atomic_and_concurrency_rejects_stale_edits(ledger):
    confirm('P001');version=shop.load()['version']
    def attempt(n):
        try:
            shop.sync('P001',[part(quantity=n)],version,'concurrency test')
            return True
        except core.WorkflowError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,[4,6]))==[False,True]
    before=shop.load()
    with pytest.raises(core.WorkflowError):
        sync('P001',[part(),part()])
    assert shop.load()==before


def test_supplier_link_requires_verified_specific_product_and_evidence(ledger):
    confirm('P001');key=sync('P001',[part()])['items'][0]['id']
    for url in ['javascript:alert(1)','https://mall.jd.com/index-12045041.html','https://evil.test/products/1','https://item.jd.com/']:
        with pytest.raises(core.WorkflowError):
            shop.supplier(key,'available',url,'synthetic evidence',shop.load()['version'])
    # Synthetic URL tests transport/format only, never claims a real product was verified.
    url='https://item.jd.com/123456789.html'
    result=shop.supplier(key,'available',url,'TEST ONLY: hypothetical SKU evidence',shop.load()['version'])
    assert result['items'][0]['supplier']['url']==url
    result=shop.supplier(key,'unavailable',None,'TEST: not stocked',shop.load()['version'])
    assert result['items'][0]['supplier']['url'] is None
    assert result['items'][0]['supplier']['status']=='unavailable'


def test_api_context_and_project_association(ledger):
    confirm('P001');sync('P001',[part()])
    client=TestClient(app)
    assert client.get('/api/shop').json()['items'][0]['sources'][0]['project_id']=='P001'
    assert client.get('/api/shop?project=P002').json()['items']==[]
    assert client.get('/api/projects/P001').json()['shop']['count']==1
    assert client.post('/api/shop',json={}).status_code==405
    assert core.context('测试项目甲')['shopping']['projects']['P001']['decision']['quote']=='测试用户明确决定制作'


def test_separate_cli_sessions_share_state(ledger):
    code=Path(__file__).resolve().parents[1]
    env={**os.environ,'PRINTLAB_ROOT':str(ledger),'PYTHONPATH':str(code)}
    def cli(*args):
        result=subprocess.run([sys.executable,'-m','printlab.cli','shop',*args],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    cli('confirm','P001','--quote','测试制作决定','--source','isolated-session-A','--expect','0')
    path=ledger/'parts.json';path.write_text(json.dumps([part()]))
    cli('sync','P001','--file',str(path),'--source','isolated-session-B','--expect','1')
    result=cli('list','测试项目甲')
    key=result['items'][0]['id']
    cli('stock',key,'--existing','0','--purchased','4','--note','TEST ONLY','--expect','2')
    assert cli('list')['items'][0]['status']=='purchased'


def test_ledger_symlink_rejected(ledger):
    secret=ledger/'Runtime/secret.json';core.write_json(secret,{'secret':'not a ledger'})
    target=ledger/shop.STORE;target.parent.mkdir(parents=True);target.symlink_to(secret)
    with pytest.raises(core.WorkflowError,match='Symbolic'):
        shop.load()


@pytest.mark.parametrize('quantity',[-1,True,1.5,'2',0])
def test_invalid_quantities_rejected(ledger,quantity):
    confirm('P001')
    with pytest.raises(core.WorkflowError):
        sync('P001',[part(quantity=quantity)])
