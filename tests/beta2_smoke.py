"""Black-box end-to-end beta smoke on a disposable DB and isolated loopback port."""
from __future__ import annotations
import json,os,secrets,socket,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix="russia-mmo-e2e-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            port=sock.getsockname()[1]
        env=os.environ.copy()
        env["RUSSIA_MMO_PORT"]=str(port)
        env["RUSSIA_MMO_BIND"]="127.0.0.1"
        env["RUSSIA_MMO_DB"]=str(Path(temp)/"test.sqlite3")
        with open(Path(temp)/"server.log","w") as log:
            proc=subprocess.Popen([sys.executable,"-u","server.py"],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            base=f"http://127.0.0.1:{port}"
            def req(path,body=None,token=None):
                headers={"Content-Type":"application/json"}
                if token:headers["Authorization"]="Bearer "+token
                request=urllib.request.Request(base+path,
                    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
                    headers=headers,method="POST" if body is not None else "GET")
                try:
                    with urllib.request.urlopen(request,timeout=10) as r:
                        return json.loads(r.read().decode())
                except urllib.error.HTTPError as e:
                    raise AssertionError(f"{path}: HTTP {e.code}: {e.read().decode()}") from e
            try:
                for i in range(100):
                    if proc.poll() is not None:break
                    try:
                        req("/health");break
                    except (OSError,AssertionError):
                        time.sleep(.1)
                assert proc.poll() is None,("server crashed",Path(temp,"server.log").read_text()[-1000:])
                status=req("/health")
                assert status["ok"] and status["version"]=="0.2"
                world=req("/api/world")
                assert world["ai_companies"]==100 and world["automated"]
                assert len(req("/api/catalog")["enterprises"])==45
                assert len(req("/api/goods")["goods"])==300
                password="Testrun_"+secrets.token_hex(8)
                seller=req("/api/register",{"username":"sellertest","password":password,"city":"Уфа"})
                buyer=req("/api/register",{"username":"buyertest","password":password,"city":"Москва"})
                local=req("/api/register",{"username":"localtest","password":password,"city":"Уфа"})
                seller_token=seller["token"];buyer_token=buyer["token"];local_token=local["token"]
                assert req("/api/login",{"username":"sellertest","password":password})["player"]==seller["player"]
                # A new login replaces the token; use the new one.
                seller_token=req("/api/login",{"username":"sellertest","password":password})["token"]
                farm=req("/api/build",{"enterprise_id":"ENT-001","city":"Уфа","x":0,"y":0,"size":2,
                    "operation":"e2e:build:farm"},seller_token)
                assert farm["size"]==2 and farm["id"]>0
                again=req("/api/build",{"enterprise_id":"ENT-001","city":"Уфа","x":0,"y":0,"size":2,
                    "operation":"e2e:build:farm"},seller_token)
                assert again["id"]==farm["id"]
                assert req("/api/upgrade",{"building_id":farm["id"],
                    "operation":"e2e:upgrade:farm"},seller_token)["level"]==2
                sources=req("/api/sources?building_id="+str(farm["id"]),token=seller_token)
                assert any(row["sku"]=="AGRI-001" for row in sources["goods"])
                harvested=req("/api/harvest",{"building_id":farm["id"],"sku":"AGRI-001","qty":3000,
                    "operation":"e2e:harvest:wheat"},seller_token)
                assert harvested["qty"]==3000
                shop=req("/api/build",{"enterprise_id":"ENT-041","city":"Уфа","x":3,"y":0,"size":1,
                    "operation":"e2e:build:shop"},seller_token)
                sale=req("/api/retail",{"building_id":shop["id"],"sku":"AGRI-001","qty":4,"price":100,
                    "operation":"e2e:retail:wheat"},seller_token)
                assert sale["revenue"]==400
                mill=req("/api/build",{"enterprise_id":"ENT-007","city":"Уфа","x":5,"y":0,"size":1,
                    "operation":"e2e:build:mill"},seller_token)
                recipes=req("/api/recipes?building_id="+str(mill["id"]),token=seller_token)["recipes"]
                r=next(x for x in recipes if x["goods_id"]=="FOOD-039" and
                       all(y["goods_id"]=="AGRI-001" for y in x["inputs"]))
                produced=req("/api/produce",{"building_id":mill["id"],"recipe_id":r["id"],
                    "operation":"e2e:produce:flour"},seller_token)
                assert produced["goods_id"]=="FOOD-039"
                assert req("/api/automation",{"building_id":mill["id"],"recipe_id":r["id"],
                    "enabled":True,"operation":"e2e:auto:mill"},seller_token)["enabled"]
                # Client orders trade within the same city.
                buy=req("/api/order",{"operation":"e2e:order:buy","side":"buy","sku":"AGRI-001",
                    "qty":20,"price":50},local_token)
                sell=req("/api/order",{"operation":"e2e:order:sell","side":"sell","sku":"AGRI-001",
                    "qty":20,"price":45},seller_token)
                assert sell["matched"]>=1
                assert any(o["id"]=="e2e:order:sell" for o in req("/api/book",token=seller_token)["mine"])
                contract=req("/api/contract",{"operation":"e2e:contract:1",
                    "seller":seller["player"],"sku":"AGRI-001","qty":5,"price":50},local_token)
                assert contract["id"]=="e2e:contract:1"
                outcome=req("/api/contract/fulfill",{"contract_id":"e2e:contract:1"},seller_token)
                assert outcome["qty"]==5
                shipment=req("/api/freight",{"operation":"e2e:shipment:1",
                    "seller":seller["player"],"sku":"AGRI-001","qty":10,"price":75},buyer_token)
                assert shipment["status"]=="requested"
                delivery=req("/api/freight/accept",{"shipment_id":"e2e:shipment:1"},seller_token)
                assert delivery["status"]=="transit"
                assert any(x["status"]=="transit" for x in req("/api/shipments",token=buyer_token)["shipments"])
                assert req("/api/ledger",token=seller_token)["transfers"]
                assert len(req("/api/map?city=%D0%A3%D1%84%D0%B0",token=seller_token)["buildings"])==3
                assert req("/api/profile",token=seller_token)["cash"]>=0
                print("E2E PASS: world 100 AI, registration, login, 45 enterprises, 300 goods, build, upgrade, source, mill, automation, retail, market, contract, freight, ledger")
            finally:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait()
                print("E2E_SERVER_EXIT",proc.returncode)
                if proc.returncode not in (-15,0):
                    print("E2E LOG TAIL:",Path(temp,"server.log").read_text()[-1000:])
if __name__=="__main__":main()
