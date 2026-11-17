"""M1: persistent bounded city demand and atomic limit-order matching."""
from __future__ import annotations
import json
from .economy import Economy, ceildiv

CITIES=("Москва","Санкт-Петербург","Казань","Уфа","Екатеринбург","Новосибирск","Краснодар","Ростов-на-Дону","Самара","Владивосток")

class Market(Economy):
    def __init__(self,db_path=":memory:",docs=None):
        if docs is None:super().__init__(db_path)
        else:super().__init__(db_path,docs)
        self.db.executescript("""
CREATE TABLE IF NOT EXISTS market_orders(
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, city TEXT NOT NULL, sku TEXT NOT NULL,
 side TEXT NOT NULL CHECK(side IN ('buy','sell')),
 price INTEGER NOT NULL CHECK(price>0),
 qty_total INTEGER NOT NULL CHECK(qty_total>0),
 qty_left INTEGER NOT NULL CHECK(qty_left>=0),
 status TEXT NOT NULL CHECK(status IN ('open','filled','cancelled')),
 created_tick INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS trades(
 id INTEGER PRIMARY KEY AUTOINCREMENT, buy_id TEXT NOT NULL, sell_id TEXT NOT NULL,
 buyer TEXT NOT NULL, seller TEXT NOT NULL, city TEXT NOT NULL, sku TEXT NOT NULL,
 qty INTEGER NOT NULL CHECK(qty>0), price INTEGER NOT NULL CHECK(price>0), tick INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS city_demand(
 city TEXT NOT NULL,sku TEXT NOT NULL,day INTEGER NOT NULL,
 budget_kopecks INTEGER NOT NULL CHECK(budget_kopecks>=0),
 spent_kopecks INTEGER NOT NULL DEFAULT 0 CHECK(spent_kopecks>=0),
 qty_limit INTEGER NOT NULL CHECK(qty_limit>=0),
 qty_bought INTEGER NOT NULL DEFAULT 0 CHECK(qty_bought>=0),
 PRIMARY KEY(city,sku,day)
);
CREATE TABLE IF NOT EXISTS import_limits(
 city TEXT NOT NULL,sku TEXT NOT NULL,day INTEGER NOT NULL,
 qty_limit INTEGER NOT NULL CHECK(qty_limit>=0),
 used INTEGER NOT NULL DEFAULT 0 CHECK(used>=0),
 PRIMARY KEY(city,sku,day)
);
CREATE INDEX IF NOT EXISTS order_match ON market_orders(city,sku,side,status,price,created_tick,id);
""")
    def _city(self,city):
        if city not in CITIES:raise ValueError("unknown city")
    def _company_city(self,owner):
        row=self.db.execute("SELECT city FROM companies WHERE id=?",(owner,)).fetchone()
        if not row:raise ValueError("unknown company")
        return row[0]
    def _available_cash(self,owner):
        return self.balance(owner)-self._reserved_purchase_funds(owner)
    def _available_stock(self,owner,sku):
        return self.inventory(owner,sku)-self._reserved_sale_qty(owner,sku)
    def import_goods(self,op,buyer,sku,qty,unit_price,quota,source="system_import"):
        # M1 must not spend funds already committed to open bids.
        kind=self._key("import",buyer,sku,qty,unit_price,quota,source)
        cached=self._check(op,kind)
        if cached is not None:return cached
        if type(qty)==int and type(unit_price)==int and qty>0 and unit_price>0:
            if self._available_cash(buyer)<qty*unit_price:raise ValueError("cash reserved for open bids")
        return super().import_goods(op,buyer,sku,qty,unit_price,quota,source)
    def trade(self,op,buyer,seller,sku,qty,unit_price):
        # Direct trade must not consume escrowed order resources.
        kind=self._key("trade",buyer,seller,sku,qty,unit_price)
        cached=self._check(op,kind)
        if cached is not None:return cached
        if type(qty)==int and type(unit_price)==int and qty>0 and unit_price>0:
            if self._available_cash(buyer)<qty*unit_price:raise ValueError("cash reserved for open bids")
            if self._available_stock(seller,sku)<qty:raise ValueError("stock reserved for open asks")
        return super().trade(op,buyer,seller,sku,qty,unit_price)
    def produce(self,op,company,recipe_id,batches=1,electricity_kopecks_kwh=900,labor_kopecks_min=45,utility="utility"):
        kind=self._key("production",company,recipe_id,batches,electricity_kopecks_kwh,labor_kopecks_min,utility)
        cached=self._check(op,kind)
        if cached is not None:return cached
        if recipe_id in self.recipes and type(batches)==int and batches>0:
            r=self.recipes[recipe_id]
            if any(self._available_stock(company,i["goods_id"])<i["quantity"]*batches for i in r["inputs"]):
                raise ValueError("production inputs reserved for open asks")
            if all(type(v)==int and v>=0 for v in (electricity_kopecks_kwh,labor_kopecks_min)):
                cost=(ceildiv(r["electricity_wh"]*electricity_kopecks_kwh,1000)+
                      r["labor_minutes"]*labor_kopecks_min)*batches
                if self._available_cash(company)<cost:raise ValueError("cash reserved for open bids")
        return super().produce(op,company,recipe_id,batches,electricity_kopecks_kwh,labor_kopecks_min,utility)
    def _order(self,order_id):
        r=self.db.execute("SELECT * FROM market_orders WHERE id=?",(order_id,)).fetchone()
        return dict(r) if r else None
    def place_order(self,order_id,owner,sku,side,qty,price,city=None):
        if side not in ("buy","sell") or sku not in self.goods:raise ValueError("invalid order")
        if any(type(x)!=int or x<=0 for x in (qty,price)):raise ValueError("invalid integer price or quantity")
        city=city or self._company_city(owner)
        self._city(city)
        if city!=self._company_city(owner):raise ValueError("no remote order without logistics")
        with self.atomic():
            cached=self._order(order_id)
            if cached:
                if any(cached[k]!=v for k,v in {"owner":owner,"sku":sku,"side":side,"qty_total":qty,"price":price,"city":city}.items()):
                    raise ValueError("order id collision")
                return cached
            if side=="sell" and self.inventory(owner,sku)<qty+self._reserved_sale_qty(owner,sku):
                raise ValueError("insufficient unreserved stock")
            if side=="buy" and self.balance(owner)<qty*price+self._reserved_purchase_funds(owner):
                raise ValueError("insufficient unreserved cash")
            self.db.execute("INSERT INTO market_orders VALUES(?,?,?,?,?,?,?,?,?,?)",
                (order_id,owner,city,sku,side,price,qty,qty,"open",self.tick()))
            return self._order(order_id)
    def _reserved_sale_qty(self,owner,sku):
        return int(self.db.execute("SELECT COALESCE(SUM(qty_left),0) FROM market_orders WHERE owner=? AND sku=? AND side='sell' AND status='open'",(owner,sku)).fetchone()[0])
    def _reserved_purchase_funds(self,owner):
        return int(self.db.execute("SELECT COALESCE(SUM(qty_left*price),0) FROM market_orders WHERE owner=? AND side='buy' AND status='open'",(owner,)).fetchone()[0])
    def cancel_order(self,order_id,owner):
        with self.atomic():
            o=self._order(order_id)
            if not o or o["owner"]!=owner:raise ValueError("unknown order or owner")
            if o["status"]=="open":
                self.db.execute("UPDATE market_orders SET status='cancelled' WHERE id=?",(order_id,))
            return self._order(order_id)
    def match(self,city,sku,max_trades=100):
        self._city(city)
        if sku not in self.goods:raise ValueError("unknown sku")
        if type(max_trades)!=int or max_trades<=0:raise ValueError("bad max trades")
        matched=[]
        with self.atomic():
            for _ in range(max_trades):
                buys=self.db.execute("SELECT * FROM market_orders WHERE city=? AND sku=? AND side='buy' AND status='open' ORDER BY price DESC,created_tick,id",(city,sku)).fetchall()
                sells=self.db.execute("SELECT * FROM market_orders WHERE city=? AND sku=? AND side='sell' AND status='open' ORDER BY price ASC,created_tick,id",(city,sku)).fetchall()
                chosen=None
                for b in buys:
                    for s in sells:
                        if b["price"]<s["price"]:break
                        if b["owner"]!=s["owner"]:
                            chosen=(b,s);break
                    if chosen:break
                if chosen is None:break
                b,s=chosen
                qty=min(b["qty_left"],s["qty_left"])
                price=s["price"] if (s["created_tick"],s["id"])<=(b["created_tick"],b["id"]) else b["price"]
                assert price<=b["price"] and price>=s["price"]
                result=super().trade(f"market:{b['id']}:{s['id']}:{b['qty_left']}:{s['qty_left']}",b["owner"],s["owner"],sku,qty,price)
                for o in (b,s):
                    remaining=o["qty_left"]-qty
                    self.db.execute("UPDATE market_orders SET qty_left=?,status=? WHERE id=?",
                        (remaining,"open" if remaining else "filled",o["id"]))
                self.db.execute("INSERT INTO trades(buy_id,sell_id,buyer,seller,city,sku,qty,price,tick) VALUES(?,?,?,?,?,?,?,?,?)",
                    (b["id"],s["id"],b["owner"],s["owner"],city,sku,qty,price,self.tick()))
                matched.append(dict(result,city=city,sku=sku,price=price))
        return matched
    def set_demand(self,city,sku,day,budget_kopecks,qty_limit):
        self._city(city)
        if sku not in self.goods or any(type(x)!=int or x<0 for x in (day,budget_kopecks,qty_limit)):raise ValueError("invalid demand")
        with self.atomic():
            row=self.db.execute("SELECT 1 FROM city_demand WHERE city=? AND sku=? AND day=?",(city,sku,day)).fetchone()
            if row:raise ValueError("daily demand already configured")
            self.db.execute("INSERT INTO city_demand(city,sku,day,budget_kopecks,qty_limit) VALUES(?,?,?,?,?)",(city,sku,day,budget_kopecks,qty_limit))
    def add_import_limit(self,city,sku,day,qty_limit):
        self._city(city)
        if sku not in self.goods or any(type(v)!=int or v<0 for v in (day,qty_limit)):raise ValueError("invalid import quota")
        self.db.execute("INSERT INTO import_limits(city,sku,day,qty_limit) VALUES(?,?,?,?)",(city,sku,day,qty_limit))
    def import_city(self,op,buyer,sku,qty,price):
        city=self._company_city(buyer)
        if type(qty)!=int or qty<=0:raise ValueError("invalid import qty")
        with self.atomic():
            cached=self._check(op,self._key("import",buyer,sku,qty,price,qty,"system_import"))
            if cached is not None:return cached
            row=self.db.execute("SELECT * FROM import_limits WHERE city=? AND sku=? AND day=?",(city,sku,self.tick())).fetchone()
            if row is None or row["used"]+qty>row["qty_limit"]:raise ValueError("city import quota exceeded")
            result=self.import_goods(op,buyer,sku,qty,price,qty)
            self.db.execute("UPDATE import_limits SET used=used+? WHERE city=? AND sku=? AND day=?",(qty,city,sku,self.tick()))
            return result
    def household_purchase(self,op,city,sku,seller,qty,price,household_account):
        self._city(city)
        if self._company_city(seller)!=city or self._company_city(household_account)!=city:raise ValueError("cross-city household purchase")
        if type(qty)!=int or qty<=0 or type(price)!=int or price<=0:raise ValueError("bad purchase")
        with self.atomic():
            cached=self._check(op,self._key("trade",household_account,seller,sku,qty,price))
            if cached is not None:return cached
            row=self.db.execute("SELECT * FROM city_demand WHERE city=? AND sku=? AND day=?",(city,sku,self.tick())).fetchone()
            if row is None or row["qty_bought"]+qty>row["qty_limit"] or row["spent_kopecks"]+qty*price>row["budget_kopecks"]:
                raise ValueError("city demand cap reached")
            result=self.trade(op,household_account,seller,sku,qty,price)
            self.db.execute("UPDATE city_demand SET qty_bought=qty_bought+?,spent_kopecks=spent_kopecks+? WHERE city=? AND sku=? AND day=?",
                (qty,qty*price,city,sku,self.tick()))
            return result
