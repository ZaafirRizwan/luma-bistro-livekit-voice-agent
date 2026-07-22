"""Deterministic assessment checks against the supplied mock API."""
from fastapi.testclient import TestClient
from app import app

c = TestClient(app)
def reset(): c.post('/admin/reset')
def create(key, **values): return c.post('/reservations',headers={'Idempotency-Key':key},json=values)

def t1():
    reset(); a=c.get('/availability',params={'date':'2026-08-14','time':'18:00','party_size':4}); assert a.json()['available']
    r=create('t1',name='Jordan Lee',phone='310-555-0199',date='2026-08-14',time='18:00',party_size=4,notes=None); assert r.status_code==200
def t2():
    reset(); a=c.get('/availability',params={'date':'2026-08-14','time':'18:30','party_size':4}).json(); assert not a['available'] and a['alternatives'][0]['time']=='17:30'
    r=create('t2',name='Taylor Kim',phone='424-555-0188',date='2026-08-14',time='19:30',party_size=4); assert r.status_code==200
def t3():
    reset(); r=create('t3',name='Casey Brown',phone='213-555-0114',date='2026-08-15',time='18:30',party_size=4); assert r.json()['party_size']==4
def t4():
    reset(); found=c.get('/reservations/search',params={'confirmation_code':'LUMA-4821'}).json()['results'][0]; r=c.patch('/reservations/'+found['reservation_id'],json={'time':'19:30','party_size':4}); assert r.status_code==200 and r.json()['time']=='19:30'
def t5():
    reset(); r=c.post('/reservations/res_existing_4821/cancel'); assert r.status_code==200 and r.json()['status']=='cancelled'
def t6():
    reset(); first=c.get('/availability',params={'date':'2026-08-16','time':'18:00','party_size':2}); second=c.get('/availability',params={'date':'2026-08-16','time':'18:00','party_size':2}); assert first.status_code==503 and second.json()['available']
def t7():
    reset(); payload={'name':'Morgan Reed','phone':'310-555-0166','date':'2026-08-14','time':'20:00','party_size':2}; a=create('same-key',**payload); b=create('same-key',**payload); assert a.json()['reservation_id']==b.json()['reservation_id']

if __name__ == '__main__':
    for name in ('t1','t2','t3','t4','t5','t6','t7'):
        globals()[name](); print(name.upper(), 'PASS')
