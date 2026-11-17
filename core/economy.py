"""RussiaEconomicMMO M0: deterministic integer accounting and stock simulator."""
from __future__ import annotations
import json,sqlite3,hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs"

def ceildiv(a:int,b:int)->int:
    if b<=0:raise ValueError("nonpositive divisor")
    return (a+b-1)//b

class Economy:
    def __init__(self,db_path=":memory:",docs=DOCS):
        self.goods={x["goods_id"]:x for x in json.loads((Path(docs)/"PRODUCTION-CATALOG-1.0-GOODS.json").read_text())["goods"]}
        self.recipes={x["recipe_id"]:x for x in json.loads((Path(docs)/"PRODUCTION-CATALOG-1.0-RECIPES.json").read_text())["recipes"]}
        self.db=sqlite3.connect(str(db_path),isolation_level=None,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY,city TEXT NOT NULL,kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(owner TEXT PRIMARY KEY,balance INTEGER NOT NULL CHECK(balance>=0));
CREATE TABLE IF NOT EXISTS lots(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,goods_id TEXT NOT NULL,qty INTEGER NOT NULL CHECK(qty>=0),cost_total INTEGER NOT NULL CHECK(cost_total>=0),created_tick INTEGER NOT NULL,expires_tick INTEGER);
CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY AUTOINCREMENT,operation TEXT UNIQUE NOT NULL,source TEXT NOT NULL,destination TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>=0),tick INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS events(operation TEXT PRIMARY KEY,kind TEXT NOT NULL,result_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contracts(id TEXT PRIMARY KEY,buyer TEXT NOT NULL,seller TEXT NOT NULL,goods_id TEXT NOT NULL,qty INTEGER NOT NULL CHECK(qty>0),unit_price INTEGER NOT NULL CHECK(unit_price>0),status TEXT NOT NULL CHECK(status IN ('open','fulfilled','cancelled')));
CREATE TABLE IF NOT EXISTS facilities(id TEXT PRIMARY KEY,owner TEXT NOT NULL,enterprise_id TEXT NOT NULL,capacity_batches_day INTEGER NOT NULL CHECK(capacity_batches_day>0));
CREATE TABLE IF NOT EXISTS facility_usage(facility_id TEXT NOT NULL,tick INTEGER NOT NULL,batches INTEGER NOT NULL,PRIMARY KEY(facility_id,tick));
CREATE TABLE IF NOT EXISTS clock(id INTEGER PRIMARY KEY CHECK(id=1),tick INTEGER NOT NULL);
INSERT OR IGNORE INTO clock VALUES(1,0);
CREATE INDEX IF NOT EXISTS lots_lookup ON lots(owner,goods_id,expires_tick,id);
""")
    @contextmanager
    def atomic(self):
        nested=self.db.in_transaction
        if nested:self.db.execute("SAVEPOINT nested_tx")
        else:self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            if nested:
                self.db.execute("ROLLBACK TO SAVEPOINT nested_tx")
                self.db.execute("RELEASE SAVEPOINT nested_tx")
            else:self.db.execute("ROLLBACK")
            raise
        else:
            if nested:self.db.execute("RELEASE SAVEPOINT nested_tx")
            else:self.db.execute("COMMIT")
    def close(self):self.db.close()
    def tick(self)->int:return int(self.db.execute("SELECT tick FROM clock WHERE id=1").fetchone()[0])
    def advance(self,days:int=1)->int:
        if not isinstance(days,int) or days<=0:raise ValueError("days must be positive integer")
        self.db.execute("UPDATE clock SET tick=tick+? WHERE id=1",(days,))
        return self.tick()
    def create_company(self,id:str,city:str,initial_cash:int=0,kind="player")->None:
        if not id or not city or type(initial_cash)!=int or initial_cash<0:raise ValueError("invalid company")
        with self.atomic():
            self.db.execute("INSERT INTO companies VALUES(?,?,?)",(id,city,kind))
            self.db.execute("INSERT INTO accounts VALUES(?,?)",(id,initial_cash))
    def balance(self,owner:str)->int:
        row=self.db.execute("SELECT balance FROM accounts WHERE owner=?",(owner,)).fetchone()
        if row is None:raise ValueError("unknown account")
        return int(row[0])
    def inventory(self,owner:str,sku:str)->int:
        return int(self.db.execute("SELECT COALESCE(SUM(qty),0) FROM lots WHERE owner=? AND goods_id=?",(owner,sku)).fetchone()[0])
    def _key(self,kind,*args):
        payload=json.dumps([kind,*args],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        return kind+":"+hashlib.sha256(payload.encode()).hexdigest()
    def _check(self,op,kind):
        row=self.db.execute("SELECT kind,result_json FROM events WHERE operation=?",(op,)).fetchone()
        if row:
            if row["kind"]!=kind:raise ValueError("operation id reused for different type")
            return json.loads(row["result_json"])
        return None
    def _event(self,op,kind,result):
        self.db.execute("INSERT INTO events VALUES(?,?,?)",(op,kind,json.dumps(result,sort_keys=True)))
        return result
    def _transfer(self,op,source,destination,amount):
        if type(amount)!=int or amount<0:raise ValueError("invalid amount")
        if self.balance(source)<amount:raise ValueError("insufficient funds")
        self.balance(destination)
        self.db.execute("UPDATE accounts SET balance=balance-? WHERE owner=?",(amount,source))
        self.db.execute("UPDATE accounts SET balance=balance+? WHERE owner=?",(amount,destination))
        self.db.execute("INSERT INTO transfers(operation,source,destination,amount,tick) VALUES(?,?,?,?,?)",(op,source,destination,amount,self.tick()))
    def _consume(self,owner,sku,qty):
        if type(qty)!=int or qty<=0:raise ValueError("invalid quantity")
        if self.inventory(owner,sku)<qty:raise ValueError(f"insufficient stock {sku}")
        rows=self.db.execute("SELECT id,qty,cost_total FROM lots WHERE owner=? AND goods_id=? AND qty>0 ORDER BY CASE WHEN expires_tick IS NULL THEN 1 ELSE 0 END,expires_tick,id",(owner,sku)).fetchall()
        need=qty;cost=0
        for row in rows:
            if need==0:break
            taken=min(need,row["qty"])
            used=ceildiv(row["cost_total"]*taken,row["qty"]) if taken<row["qty"] else row["cost_total"]
            self.db.execute("UPDATE lots SET qty=qty-?,cost_total=cost_total-? WHERE id=?",(taken,used,row["id"]))
            cost+=used;need-=taken
        assert need==0
        return cost
    def _lot(self,owner,sku,qty,cost):
        if sku not in self.goods or type(qty)!=int or qty<=0 or type(cost)!=int or cost<0:raise ValueError("invalid lot")
        self.db.execute("INSERT INTO lots(owner,goods_id,qty,cost_total,created_tick) VALUES(?,?,?,?,?)",(owner,sku,qty,cost,self.tick()))
    def import_goods(self,op,buyer,sku,qty,unit_price,quota,source="system_import"):
        if buyer==source:raise ValueError("cannot import goods from own supply account")
        if sku not in self.goods or self.goods[sku]["source_mode"]=="manufacturing":raise ValueError("import only primary supply in M0")
        if any(type(x)!=int or x<=0 for x in (qty,unit_price,quota)):raise ValueError("positive integers required")
        if qty>quota:raise ValueError("quota exceeded")
        kind=self._key("import",buyer,sku,qty,unit_price,quota,source)
        with self.atomic():
            cached=self._check(op,kind)
            if cached is not None:return cached
            self._transfer(op,buyer,source,qty*unit_price)
            self._lot(buyer,sku,qty,qty*unit_price)
            return self._event(op,kind,{"sku":sku,"qty":qty,"spent":qty*unit_price})
    def trade(self,op,buyer,seller,sku,qty,unit_price):
        if buyer==seller or sku not in self.goods:raise ValueError("invalid trade")
        if any(type(x)!=int or x<=0 for x in (qty,unit_price)):raise ValueError("invalid trade quantities")
        kind=self._key("trade",buyer,seller,sku,qty,unit_price)
        with self.atomic():
            cached=self._check(op,kind)
            if cached is not None:return cached
            if self.inventory(seller,sku)<qty:raise ValueError("seller out of stock")
            self._transfer(op,buyer,seller,qty*unit_price)
            cogs=self._consume(seller,sku,qty)
            self._lot(buyer,sku,qty,qty*unit_price)
            return self._event(op,kind,{"qty":qty,"paid":qty*unit_price,"seller_cogs":cogs,"seller_gross_profit":qty*unit_price-cogs})
    def produce(self,op,company,recipe_id,batches=1,electricity_kopecks_kwh=900,labor_kopecks_min=45,utility="utility"):
        if recipe_id not in self.recipes:raise ValueError("unknown recipe")
        if type(batches)!=int or batches<=0:raise ValueError("invalid batches")
        if any(type(x)!=int or x<0 for x in (electricity_kopecks_kwh,labor_kopecks_min)):raise ValueError("invalid tariff")
        r=self.recipes[recipe_id]
        kind=self._key("production",company,recipe_id,batches,electricity_kopecks_kwh,labor_kopecks_min,utility)
        with self.atomic():
            cached=self._check(op,kind)
            if cached is not None:return cached
            for x in r["inputs"]:
                if self.inventory(company,x["goods_id"])<x["quantity"]*batches:raise ValueError(f"insufficient stock {x['goods_id']}")
            electricity_cost=ceildiv(r["electricity_wh"]*electricity_kopecks_kwh,1000)*batches
            wage_cost=r["labor_minutes"]*labor_kopecks_min*batches
            costs=electricity_cost+wage_cost
            if self.balance(company)<costs:raise ValueError("insufficient cash for utilities and labor")
            city_row=self.db.execute("SELECT city FROM companies WHERE id=?",(company,)).fetchone()
            household=("household:"+city_row[0]) if city_row else utility
            if not self.db.execute("SELECT 1 FROM accounts WHERE owner=?",(household,)).fetchone():
                household=utility
            self._transfer(op+":energy",company,utility,electricity_cost)
            self._transfer(op+":wages",company,household,wage_cost)
            input_cost=sum(self._consume(company,x["goods_id"],x["quantity"]*batches) for x in r["inputs"])
            # one output per current catalog recipe; coproducts recorded but not sellable
            assert len(r["outputs"])==1
            o=r["outputs"][0]
            self._lot(company,o["goods_id"],o["quantity"]*batches,input_cost+costs)
            return self._event(op,kind,{"goods_id":o["goods_id"],"qty":o["quantity"]*batches,"cost":input_cost+costs,"input_cost":input_cost,"operating_cost":costs,"recipe":recipe_id})
    def create_facility(self,facility_id,owner,enterprise_id,capacity_batches_day=1):
        if type(capacity_batches_day)!=int or capacity_batches_day<=0:raise ValueError("invalid capacity")
        self.balance(owner)
        if not enterprise_id.startswith("ENT-"):raise ValueError("invalid enterprise")
        with self.atomic():
            self.db.execute("INSERT INTO facilities VALUES(?,?,?,?)",(facility_id,owner,enterprise_id,capacity_batches_day))
    def produce_at(self,op,company,facility_id,recipe_id,batches=1):
        if recipe_id not in self.recipes:raise ValueError("unknown recipe")
        r=self.recipes[recipe_id]
        if type(batches)!=int or batches<=0:raise ValueError("invalid batches")
        with self.atomic():
            row=self.db.execute("SELECT * FROM facilities WHERE id=?",(facility_id,)).fetchone()
            if row is None or row["owner"]!=company or row["enterprise_id"]!=r["enterprise_id"]:
                raise ValueError("incompatible facility")
            key=self._key("production",company,recipe_id,batches,900,45,"utility")
            cached=self._check(op,key)
            if cached is not None:return cached
            used=self.db.execute("SELECT batches FROM facility_usage WHERE facility_id=? AND tick=?",(facility_id,self.tick())).fetchone()
            if (used[0] if used else 0)+batches>row["capacity_batches_day"]:
                raise ValueError("daily capacity exceeded")
            result=self.produce(op,company,recipe_id,batches)
            self.db.execute("""INSERT INTO facility_usage(facility_id,tick,batches) VALUES(?,?,?)
ON CONFLICT(facility_id,tick) DO UPDATE SET batches=batches+excluded.batches""",(facility_id,self.tick(),batches))
            return result
    def create_contract(self,id,buyer,seller,sku,qty,unit_price):
        if sku not in self.goods or buyer==seller or type(qty)!=int or qty<=0 or type(unit_price)!=int or unit_price<=0:raise ValueError("invalid contract")
        self.balance(buyer);self.balance(seller)
        with self.atomic():
            self.db.execute("INSERT INTO contracts VALUES(?,?,?,?,?,?,?)",(id,buyer,seller,sku,qty,unit_price,"open"))
    def fulfill_contract(self,contract_id):
        with self.atomic():
            row=self.db.execute("SELECT * FROM contracts WHERE id=?",(contract_id,)).fetchone()
            if row is None:raise ValueError("unknown contract")
            kind=self._key("trade",row["buyer"],row["seller"],row["goods_id"],row["qty"],row["unit_price"])
            if row["status"]=="fulfilled":
                return self._check("contract:"+contract_id,kind)
            if row["status"]!="open":raise ValueError("contract not open")
            result=self.trade("contract:"+contract_id,row["buyer"],row["seller"],row["goods_id"],row["qty"],row["unit_price"])
            self.db.execute("UPDATE contracts SET status='fulfilled' WHERE id=?",(contract_id,))
            return result
    def total_money(self):
        return int(self.db.execute("SELECT COALESCE(SUM(balance),0) FROM accounts").fetchone()[0])
