"""RussiaEconomicMMO isolated beta API. Python standard library only."""
from __future__ import annotations
import json,sqlite3,threading,secrets,hashlib,hmac,os,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from core.market import Market,CITIES
from core.beta_features import BetaFeatures,SHOP_TYPES
from core.world import WorldEngine

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get("RUSSIA_MMO_DB",str(ROOT/"runtime"/"beta.sqlite3")))
DB.parent.mkdir(exist_ok=True)
E=Market(str(DB))
LOCK=threading.RLock()
E.db.executescript("""
CREATE TABLE IF NOT EXISTS players(
 id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,passhash TEXT NOT NULL,salt TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS buildings(
 id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,enterprise_id TEXT NOT NULL,
 city TEXT NOT NULL,x INTEGER NOT NULL,y INTEGER NOT NULL,
 created_tick INTEGER NOT NULL,UNIQUE(city,x,y)
);
CREATE TABLE IF NOT EXISTS building_orders(
 operation TEXT PRIMARY KEY,owner TEXT NOT NULL,building_id INTEGER NOT NULL
);
""")
B=BetaFeatures(E)
WORLD=WorldEngine(E,B)
ENTERPRISES=json.loads((ROOT/"docs/PRODUCTION-CATALOG-1.0-EQUIPMENT.json").read_text())["enterprises"]
ENT={x["enterprise_id"]:x for x in ENTERPRISES}
NAME={}
GROUP={}
import re
text=(ROOT/"docs/PRODUCTION-CATALOG-1.0-ENTERPRISES.md").read_text()
for line in text.splitlines():
    cols=[part.strip() for part in line.split("|")]
    if len(cols)>=5 and re.fullmatch(r"ENT-\d{3}",cols[1]):
        NAME[cols[1]]=cols[3]
        GROUP[cols[1]]=cols[2]
def err(message):raise ValueError(message)
def password_hash(password,salt):
    return hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),200000).hex()
def register(username,password,city="Уфа"):
    if not 3<=len(username)<=24 or not username.replace("_","").isalnum():err("Логин: 3–24 буквы/цифры")
    if city not in CITIES:err("Выберите город из списка")
    if len(password)<8 or len(password)>128:err("Пароль: от 8 до 128 символов")
    username=username.casefold()
    with LOCK,E.atomic():
        uid="player:"+username
        token=secrets.token_urlsafe(32)
        salt=secrets.token_hex(16)
        E.db.execute("INSERT INTO players VALUES(?,?,?,?,?)",(uid,username,password_hash(password,salt),salt,hashlib.sha256(token.encode()).hexdigest()))
        E.create_company(uid,city,10_000_000,"player")
        return {"token":token,"player":uid}
def login(username,password):
    username=username.casefold()
    with LOCK:
        row=E.db.execute("SELECT * FROM players WHERE username=?",(username,)).fetchone()
        if not row or not hmac.compare_digest(row["passhash"],password_hash(password,row["salt"])):err("Неверный логин или пароль")
        token=secrets.token_urlsafe(32)
        E.db.execute("UPDATE players SET token_hash=? WHERE id=?",(hashlib.sha256(token.encode()).hexdigest(),row["id"]))
        return {"token":token,"player":row["id"]}
def identity(token):
    if not token:err("Необходим вход")
    row=E.db.execute("SELECT id FROM players WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:err("Сессия недействительна")
    return row["id"]
def profile(owner):
    with LOCK:
        buildings=B.company_buildings(owner)
        return {"owner":owner,"cash":E.balance(owner),
                "available_cash":E._available_cash(owner),
                "buildings":buildings,
                "city":E._company_city(owner),"tick":E.tick(),
                "company_count":E.db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]}
def catalog():
    return {"cities":list(CITIES),
      "enterprises":[{"id":e["enterprise_id"],"name":NAME.get(e["enterprise_id"],e["enterprise_id"]),
        "role":e.get("role",""),"category":GROUP.get(e["enterprise_id"],"Прочее"),
        "lines":len(e.get("lines",[])),
        "recipe_count":len(B.equipment.get(e["enterprise_id"],[])),
        "source_count":sum(g["source_enterprise"]==e["enterprise_id"] and g["source_mode"] in
           {"farm_or_fishery","extraction_or_utility","recovery","system_utility"} for g in E.goods.values()),
        "cost":B.build_cost(e["enterprise_id"]),"sizes":[1,2,3]} for e in ENTERPRISES],
      "goods":len(E.goods),"recipes":len(E.recipes)}
def city_map(city,owner):
    if city not in CITIES:err("Неизвестный город")
    with LOCK:
        buildings=[dict(r) for r in E.db.execute(
            "SELECT id,enterprise_id,city,x,y,owner,size FROM buildings WHERE city=?",(city,))]
        return {"city":city,"width":24,"height":16,"buildings":buildings,"owner":owner}
def construct(owner,enterprise_id,city,x,y,operation,size=1):
    with LOCK:
        result=B.build(owner,enterprise_id,city,x,y,size,operation,ENT)
        return dict(result,replayed=result.get("replayed",False))
def inventory(owner):
    with LOCK:
        rows=E.db.execute("SELECT goods_id,SUM(qty) AS qty FROM lots WHERE owner=? AND qty>0 GROUP BY goods_id ORDER BY goods_id",(owner,)).fetchall()
        return {"inventory":[dict(r) for r in rows]}
def recipes(owner,building_id):
    with LOCK:
        row=E.db.execute("SELECT enterprise_id FROM buildings WHERE id=? AND owner=?",(building_id,owner)).fetchone()
        if not row:err("Здание не найдено")
        return {"recipes":[{"id":r["recipe_id"],"goods_id":r["output_goods_id"],"inputs":r["inputs"],"outputs":r["outputs"]} for r in E.recipes.values() if r["enterprise_id"]==row["enterprise_id"]]}
def import_material(owner,sku,qty,operation):
    if sku not in E.goods or E.goods[sku]["source_mode"]=="manufacturing":err("Импортируется только первичное сырьё")
    if type(qty)!=int or qty<=0 or qty>5000:err("Количество от 1 до 5000")
    if not isinstance(operation,str) or len(operation)<8:err("Нужен ID операции")
    city=E._company_city(owner)
    with LOCK,E.atomic():
        row=E.db.execute("SELECT 1 FROM import_limits WHERE city=? AND sku=? AND day=?",(city,sku,E.tick())).fetchone()
        if row is None:E.add_import_limit(city,sku,E.tick(),10000)
        price=18 if sku.startswith("AGRI") else 12
        return E.import_city(operation,owner,sku,qty,price)
def production(owner,building_id,recipe_id,operation):
    if not isinstance(operation,str) or len(operation)<8:err("Нужен ID операции")
    with LOCK:
        row=E.db.execute("SELECT enterprise_id FROM buildings WHERE id=? AND owner=?",(building_id,owner)).fetchone()
        if not row:err("Здание не найдено")
        return E.produce_at(operation,owner,"building:"+str(building_id),recipe_id,1)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send(self,status,payload):
        raw=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def handle_api(self):
        path=urlparse(self.path).path
        if path=="/health" and self.command=="GET":return {"ok":True,"service":"RussiaEconomicMMO beta","version":"0.2"}
        if path=="/api/catalog" and self.command=="GET":return catalog()
        if path=="/api/goods" and self.command=="GET":
            return {"goods":[{"sku":g["goods_id"],"name":g["name"],
                "sector":g["sector"],"source_mode":g["source_mode"]}
                for g in E.goods.values()]}
        if path=="/api/world" and self.command=="GET":
            return WORLD.world_status()
        if self.command=="POST":
            length=int(self.headers.get("Content-Length","0"))
            if length<1 or length>8192:err("Неверный размер запроса")
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):err("Неверный запрос")
            if path=="/api/register":return register(str(data.get("username","")),str(data.get("password","")),str(data.get("city","Уфа")))
            if path=="/api/login":return login(str(data.get("username","")),str(data.get("password","")))
        else:data={}
        token=self.headers.get("Authorization","").removeprefix("Bearer ").strip()
        owner=identity(token)
        if self.command=="GET":
            if path=="/api/profile":return profile(owner)
            if path=="/api/book":
                q=parse_qs(urlparse(self.path).query)
                return B.market_view(owner,q.get("sku",[None])[0])
            if path=="/api/contracts":return B.contracts(owner)
            if path=="/api/shipments":return B.freight_list(owner)
            if path=="/api/ledger":return B.history(owner)
            if path=="/api/companies":
                return {"companies":[{"id":r["id"],"city":r["city"],"kind":r["kind"]}
                  for r in E.db.execute("SELECT id,city,kind FROM companies WHERE kind IN ('player','ai') ORDER BY id LIMIT 150")]}
            if path=="/api/sources":
                bid=int(parse_qs(urlparse(self.path).query).get("building_id",["0"])[0])
                return B.source_catalog(owner,bid)
            if path=="/api/inventory":return inventory(owner)
            if path=="/api/recipes":
                bid=int(parse_qs(urlparse(self.path).query).get("building_id",["0"])[0])
                return recipes(owner,bid)
            if path=="/api/map":
                city=parse_qs(urlparse(self.path).query).get("city",["Уфа"])[0]
                return city_map(city,owner)
        if self.command=="POST" and path=="/api/import":
            return import_material(owner,str(data.get("sku","")),data.get("qty"),str(data.get("operation","")))
        if self.command=="POST" and path=="/api/produce":
            return production(owner,int(data.get("building_id",0)),str(data.get("recipe_id","")),str(data.get("operation","")))
        if self.command=="POST" and path=="/api/build":
            return construct(owner,str(data.get("enterprise_id","")),str(data.get("city","")),data.get("x"),data.get("y"),
                str(data.get("operation","")),data.get("size",1))
        if self.command=="POST" and path=="/api/upgrade":
            return B.upgrade(owner,int(data.get("building_id",0)),str(data.get("operation","")))
        if self.command=="POST" and path=="/api/harvest":
            return B.harvest(owner,int(data.get("building_id",0)),str(data.get("sku","")),
                data.get("qty"),str(data.get("operation","")))
        if self.command=="POST" and path=="/api/automation":
            return B.set_automation(owner,int(data.get("building_id",0)),
                str(data.get("recipe_id","")),bool(data.get("enabled",False)),
                str(data.get("operation","")))
        if self.command=="POST" and path=="/api/order":
            return B.place(owner,str(data.get("operation","")),str(data.get("sku","")),
                str(data.get("side","")),data.get("qty"),data.get("price"))
        if self.command=="POST" and path=="/api/order/cancel":
            return B.cancel(owner,str(data.get("order_id","")))
        if self.command=="POST" and path=="/api/contract":
            return B.create_contract(owner,str(data.get("operation","")),
                str(data.get("seller","")),str(data.get("sku","")),
                data.get("qty"),data.get("price"))
        if self.command=="POST" and path=="/api/contract/fulfill":
            return B.fulfill_contract(owner,str(data.get("contract_id","")))
        if self.command=="POST" and path=="/api/freight":
            return B.freight_request(owner,str(data.get("operation","")),
                str(data.get("seller","")),str(data.get("sku","")),
                data.get("qty"),data.get("price"))
        if self.command=="POST" and path=="/api/freight/accept":
            return B.freight_accept(owner,str(data.get("shipment_id","")))
        if self.command=="POST" and path=="/api/retail":
            return B.retail(owner,int(data.get("building_id",0)),
                str(data.get("sku","")),data.get("qty"),data.get("price"),str(data.get("operation","")))
        err("Маршрут не найден")
    def do_GET(self):
        try:
            with LOCK:
                payload=self.handle_api()
            self.send(200,payload)
        except (ValueError,TypeError,sqlite3.IntegrityError,json.JSONDecodeError) as ex:
            self.send(400,{"error":str(ex)})
        except Exception:
            self.send(500,{"error":"Внутренняя ошибка"})
    def do_POST(self):self.do_GET()
if __name__=="__main__":
    host=os.environ.get("RUSSIA_MMO_BIND","127.0.0.1")
    port=int(os.environ.get("RUSSIA_MMO_PORT","18783"))
    print(f"RussiaEconomicMMO beta API listening on {host}:{port}",flush=True)
    with LOCK:
        summary=WORLD.bootstrap()
    print("World initialized",summary,flush=True)
    def world_loop():
        while True:
            time.sleep(20)
            try:
                with LOCK:
                    updates=WORLD.run_due()
                if updates:print("GAME_DAY",updates,flush=True)
            except Exception as ex:
                print("World tick error:",type(ex).__name__,str(ex),flush=True)
    threading.Thread(target=world_loop,name="russia-mmo-world",daemon=True).start()
    ThreadingHTTPServer((host,port),Handler).serve_forever()
