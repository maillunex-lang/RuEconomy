"""Expanded RussiaEconomicMMO beta systems, added without changing canonical catalogs.

All business mutations require a caller-authorized company. All amounts are
integer kopecks or integer catalog units. This remains an MVP simulation.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import json, time, re
from .market import Market, CITIES

SHOP_TYPES = {"ENT-041", "ENT-042", "ENT-043"}
SOURCE_MODES = {"farm_or_fishery", "extraction_or_utility", "recovery", "system_utility"}
GAME_DAY_SECONDS = 604800 / 365  # 7 real days per 365 game days

class BetaFeatures:
    def __init__(self, e: Market):
        self.e = e
        e.db.executescript("""
CREATE TABLE IF NOT EXISTS beta_actions(
 operation TEXT PRIMARY KEY, owner TEXT NOT NULL, action TEXT NOT NULL,
 request_json TEXT NOT NULL, response_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS beta_levels(
 building_id INTEGER PRIMARY KEY, level INTEGER NOT NULL DEFAULT 1
 CHECK(level BETWEEN 1 AND 4), auto_recipe TEXT DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS beta_deposits(
 building_id INTEGER NOT NULL, sku TEXT NOT NULL,
 qty_remaining INTEGER NOT NULL CHECK(qty_remaining>=0),
 day INTEGER NOT NULL DEFAULT -1, day_taken INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(building_id,sku)
);
CREATE TABLE IF NOT EXISTS beta_freight(
 id TEXT PRIMARY KEY, buyer TEXT NOT NULL, seller TEXT NOT NULL,
 origin TEXT NOT NULL, destination TEXT NOT NULL,
 sku TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0),
 price INTEGER NOT NULL CHECK(price>0),
 status TEXT NOT NULL CHECK(status IN ('requested','transit','delivered','cancelled')),
 created_day INTEGER NOT NULL, arriving_day INTEGER DEFAULT NULL,
 input_cogs INTEGER DEFAULT NULL, freight_cost INTEGER DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS beta_world(
 id INTEGER PRIMARY KEY CHECK(id=1), last_tick_utc REAL NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS beta_daily_stats(
 day INTEGER PRIMARY KEY, ai_decisions INTEGER NOT NULL,
 trades INTEGER NOT NULL, produced INTEGER NOT NULL,
 delivered INTEGER NOT NULL, cash_supply INTEGER NOT NULL,
 note TEXT NOT NULL
);
""")
        cols={r[1] for r in e.db.execute("PRAGMA table_info(buildings)")}
        if "size" not in cols:
            e.db.execute("ALTER TABLE buildings ADD COLUMN size INTEGER NOT NULL DEFAULT 1")
        self.equipment={}
        for r in e.recipes.values():
            self.equipment.setdefault(r["enterprise_id"],[]).append(r)

    def _building(self, owner, bid):
        r=self.e.db.execute("SELECT * FROM buildings WHERE id=? AND owner=?",(bid,owner)).fetchone()
        if r is None:raise ValueError("Здание не принадлежит вашей компании")
        return dict(r)

    def _op(self, op, owner, action, payload):
        if not isinstance(op,str) or not (8<=len(op)<=128):raise ValueError("Укажите корректный ID операции")
        body=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        row=self.e.db.execute("SELECT * FROM beta_actions WHERE operation=?",(op,)).fetchone()
        if row:
            if row["owner"]!=owner or row["action"]!=action or row["request_json"]!=body:
                raise ValueError("Идентификатор операции занят другим запросом")
            return json.loads(row["response_json"])
        return None

    def _save(self,op,owner,action,payload,result):
        self.e.db.execute("INSERT INTO beta_actions VALUES(?,?,?,?,?)",
            (op,owner,action,json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")),
             json.dumps(result,ensure_ascii=False,sort_keys=True)))
        return result

    def _company_city(self,owner):
        return self.e._company_city(owner)

    def _treasury(self,city):
        name="treasury:"+city
        if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner=?",(name,)).fetchone():
            self.e.create_company(name,city,0,"system")
        return name

    def company_buildings(self,owner):
        data=[dict(r) for r in self.e.db.execute("""
SELECT b.id,b.owner,b.enterprise_id,b.city,b.x,b.y,b.size,
 COALESCE(l.level,1) AS level,l.auto_recipe
FROM buildings b LEFT JOIN beta_levels l ON l.building_id=b.id
WHERE b.owner=? ORDER BY b.id""",(owner,))]
        return data

    def build_cost(self,enterprise_id,size=1):
        if not re.fullmatch(r"ENT-\d{3}",enterprise_id):raise ValueError("Неверный тип предприятия")
        if type(size)!=int or size not in (1,2,3):raise ValueError("Размер только 1, 2 или 3")
        sector_index=int(enterprise_id[4:])
        return (240000+sector_index*18000)*(size*size)

    def is_free(self,city,x,y,size=1):
        if city not in CITIES:raise ValueError("Неизвестный город")
        if type(x)!=int or type(y)!=int or type(size)!=int or size not in (1,2,3):
            raise ValueError("Неверный участок")
        if not (0<=x and 0<=y and x+size<=24 and y+size<=16):
            raise ValueError("Здание выходит за границы участка")
        rows=self.e.db.execute("SELECT x,y,size FROM buildings WHERE city=?",(city,))
        for b in rows:
            if x<b["x"]+b["size"] and x+size>b["x"] and y<b["y"]+b["size"] and y+size>b["y"]:
                return False
        return True

    def build(self,owner,enterprise_id,city,x,y,size,op,enterprise_ids):
        if enterprise_id not in enterprise_ids:raise ValueError("Неизвестный тип здания")
        self._company_city(owner)
        cost=self.build_cost(enterprise_id,size)
        params={"enterprise":enterprise_id,"city":city,"x":x,"y":y,"size":size}
        with self.e.atomic():
            duplicate=self._op(op,owner,"build",params)
            if duplicate is not None:return duplicate
            if not self.is_free(city,x,y,size):raise ValueError("Этот участок уже занят")
            if self.e._available_cash(owner)<cost:raise ValueError("Недостаточно доступных средств")
            self.e._transfer("beta:build:"+op,owner,self._treasury(city),cost)
            cur=self.e.db.execute("""
INSERT INTO buildings(owner,enterprise_id,city,x,y,created_tick,size)
VALUES(?,?,?,?,?,?,?)""",(owner,enterprise_id,city,x,y,self.e.tick(),size))
            bid=cur.lastrowid
            self.e.db.execute("INSERT INTO beta_levels(building_id) VALUES(?)",(bid,))
            if enterprise_id in self.equipment:
                self.e.create_facility("building:"+str(bid),owner,enterprise_id,size)
            return self._save(op,owner,"build",params,
                {"id":bid,"cash":self.e.balance(owner),"cost":cost,"size":size,"replayed":False})

    def upgrade(self,owner,bid,op):
        payload={"building_id":bid}
        with self.e.atomic():
            cached=self._op(op,owner,"upgrade",payload)
            if cached is not None:return cached
            b=self._building(owner,bid)
            row=self.e.db.execute("SELECT level FROM beta_levels WHERE building_id=?",(bid,)).fetchone()
            level=row["level"] if row else 1
            if level>=4:raise ValueError("Максимальный уровень 4")
            fee=level*180000*b["size"]
            if self.e._available_cash(owner)<fee:raise ValueError("Недостаточно средств для улучшения")
            self.e._transfer("beta:upgrade:"+op,owner,self._treasury(b["city"]),fee)
            self.e.db.execute("""
INSERT INTO beta_levels(building_id,level) VALUES(?,?)
ON CONFLICT(building_id) DO UPDATE SET level=excluded.level""",(bid,level+1))
            self.e.db.execute("UPDATE facilities SET capacity_batches_day=capacity_batches_day+? WHERE id=?",
                (b["size"],"building:"+str(bid)))
            return self._save(op,owner,"upgrade",payload,{"level":level+1,"cost":fee,"cash":self.e.balance(owner)})

    def source_catalog(self,owner,bid):
        b=self._building(owner,bid)
        items=[]
        for g in self.e.goods.values():
            if g["source_enterprise"]==b["enterprise_id"] and g["source_mode"] in SOURCE_MODES:
                reserve=self.e.db.execute("SELECT qty_remaining FROM beta_deposits WHERE building_id=? AND sku=?",
                     (bid,g["goods_id"])).fetchone()
                items.append({"sku":g["goods_id"],"name":g["name"],
                             "remaining":reserve[0] if reserve else 200000,
                             "source_mode":g["source_mode"]})
        return {"building_id":bid,"goods":items}

    def harvest(self,owner,bid,sku,qty,op):
        if type(qty)!=int or qty<=0 or qty>50000:raise ValueError("Количество от 1 до 50000")
        payload={"building_id":bid,"sku":sku,"qty":qty}
        with self.e.atomic():
            cached=self._op(op,owner,"harvest",payload)
            if cached is not None:return cached
            b=self._building(owner,bid)
            g=self.e.goods.get(sku)
            if not g or g["source_enterprise"]!=b["enterprise_id"] or g["source_mode"] not in SOURCE_MODES:
                raise ValueError("Это сырьё не производится данным предприятием")
            level=self.e.db.execute("SELECT COALESCE(level,1) FROM beta_levels WHERE building_id=?",(bid,)).fetchone()
            factor=(level[0] if level else 1)*b["size"]
            cap=5000*factor
            row=self.e.db.execute("SELECT * FROM beta_deposits WHERE building_id=? AND sku=?",(bid,sku)).fetchone()
            if row is None:
                self.e.db.execute("INSERT INTO beta_deposits(building_id,sku,qty_remaining) VALUES(?,?,?)",(bid,sku,200000))
                row=self.e.db.execute("SELECT * FROM beta_deposits WHERE building_id=? AND sku=?",(bid,sku)).fetchone()
            already=row["day_taken"] if row["day"]==self.e.tick() else 0
            if qty>cap-already:raise ValueError("Суточная мощность добычи превышена")
            if qty>row["qty_remaining"]:raise ValueError("Месторождение/урожай исчерпано")
            cost=qty*4
            if self.e._available_cash(owner)<cost:raise ValueError("Недостаточно денег для добычи")
            city=b["city"];household="household:"+city
            if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner=?",(household,)).fetchone():
                household=self._treasury(city)
            self.e._transfer("beta:source:"+op,owner,household,cost)
            self.e._lot(owner,sku,qty,cost)
            self.e.db.execute("""UPDATE beta_deposits SET qty_remaining=qty_remaining-?,
day=?,day_taken=? WHERE building_id=? AND sku=?""",(qty,self.e.tick(),already+qty,bid,sku))
            return self._save(op,owner,"harvest",payload,{"sku":sku,"qty":qty,"cost":cost,"remaining":row["qty_remaining"]-qty})

    def set_automation(self,owner,bid,recipe_id,enabled,op):
        payload={"building_id":bid,"recipe_id":recipe_id,"enabled":bool(enabled)}
        with self.e.atomic():
            cached=self._op(op,owner,"automation",payload)
            if cached is not None:return cached
            b=self._building(owner,bid)
            r=self.e.recipes.get(recipe_id)
            if enabled and (not r or r["enterprise_id"]!=b["enterprise_id"]):
                raise ValueError("Рецепт несовместим со зданием")
            self.e.db.execute("""INSERT INTO beta_levels(building_id,auto_recipe) VALUES(?,?)
ON CONFLICT(building_id) DO UPDATE SET auto_recipe=excluded.auto_recipe""",
                (bid,recipe_id if enabled else None))
            return self._save(op,owner,"automation",payload,{"enabled":bool(enabled),"recipe_id":recipe_id if enabled else None})

    def auto_produce(self):
        made=0
        rows=self.e.db.execute("""SELECT b.id,b.owner,l.auto_recipe FROM buildings b
JOIN beta_levels l ON l.building_id=b.id WHERE l.auto_recipe IS NOT NULL
ORDER BY b.id""").fetchall()
        for b in rows:
            try:
                # A failed batch is not a money/stock mutation.
                self.e.produce_at("auto:"+str(b["id"])+":"+str(self.e.tick()),
                    b["owner"],"building:"+str(b["id"]),b["auto_recipe"],1)
                made+=1
            except ValueError:
                pass
        return made

    def market_view(self,owner,sku=None,limit=60):
        city=self._company_city(owner)
        if sku and sku not in self.e.goods:raise ValueError("Неизвестный товар")
        if sku:
            query="SELECT id,side,sku,price,qty_left,created_tick FROM market_orders WHERE city=? AND sku=? AND status='open' ORDER BY created_tick DESC,id LIMIT ?"
            args=(city,sku,limit)
        else:
            query="SELECT id,side,sku,price,qty_left,created_tick FROM market_orders WHERE city=? AND status='open' ORDER BY created_tick DESC,id LIMIT ?"
            args=(city,limit)
        board=[dict(r) for r in self.e.db.execute(query,args)]
        mine=[dict(r) for r in self.e.db.execute("SELECT * FROM market_orders WHERE owner=? ORDER BY created_tick DESC,id DESC LIMIT 50",(owner,))]
        return {"city":city,"orders":board,"mine":mine}

    def place(self,owner,op,sku,side,qty,price):
        if not 1<=qty<=50000 or not 1<=price<=10**9:raise ValueError("Превышен лимит заявки")
        with self.e.atomic():
            order=self.e.place_order(op,owner,sku,side,qty,price)
            deals=self.e.match(self._company_city(owner),sku,max_trades=20)
            return {"order":self.e._order(op),"matched":len(deals),"status":self.e._order(op)["status"]}

    def cancel(self,owner,op):
        return self.e.cancel_order(op,owner)

    def contracts(self,owner):
        return {"contracts":[dict(r) for r in self.e.db.execute("""
SELECT * FROM contracts WHERE buyer=? OR seller=? ORDER BY id DESC LIMIT 60""",(owner,owner))]}

    def create_contract(self,owner,op,seller,sku,qty,price):
        if seller==owner or not 1<=qty<=50000 or not 1<=price<=10**9:
            raise ValueError("Неверный контракт")
        if self._company_city(owner)!=self._company_city(seller):
            raise ValueError("Межгородской договор оформляется через доставку")
        return self.e.create_contract(op,owner,seller,sku,qty,price) or {"id":op}

    def fulfill_contract(self,owner,op):
        row=self.e.db.execute("SELECT seller FROM contracts WHERE id=?",(op,)).fetchone()
        if not row or row["seller"]!=owner:raise ValueError("Только поставщик исполняет договор")
        return self.e.fulfill_contract(op)

    def freight_list(self,owner):
        rows=self.e.db.execute("SELECT * FROM beta_freight WHERE buyer=? OR seller=? ORDER BY created_day DESC,id DESC LIMIT 50",(owner,owner))
        return {"shipments":[dict(r) for r in rows]}

    def freight_request(self,owner,id,seller,sku,qty,price):
        if not id or not isinstance(id,str) or len(id)>100:raise ValueError("Неверный ID отправки")
        if owner==seller or sku not in self.e.goods or type(qty)!=int or not 1<=qty<=50000:
            raise ValueError("Неверная отправка")
        if type(price)!=int or not 1<=price<=10**9:raise ValueError("Неверная стоимость")
        origin=self._company_city(seller)
        destination=self._company_city(owner)
        if origin==destination:raise ValueError("В одном городе используйте биржу")
        with self.e.atomic():
            old=self.e.db.execute("SELECT * FROM beta_freight WHERE id=?",(id,)).fetchone()
            if old:
                if any(old[k]!=v for k,v in {"buyer":owner,"seller":seller,"sku":sku,"qty":qty,"price":price}.items()):
                    raise ValueError("ID доставки занят")
                return dict(old)
            self.e.db.execute("""INSERT INTO beta_freight
(id,buyer,seller,origin,destination,sku,qty,price,status,created_day)
VALUES(?,?,?,?,?,?,?,?,?,?)""",(id,owner,seller,origin,destination,sku,qty,price,"requested",self.e.tick()))
            return dict(self.e.db.execute("SELECT * FROM beta_freight WHERE id=?",(id,)).fetchone())

    def freight_accept(self,owner,id):
        with self.e.atomic():
            r=self.e.db.execute("SELECT * FROM beta_freight WHERE id=?",(id,)).fetchone()
            if not r or r["seller"]!=owner:raise ValueError("Отправка недоступна")
            if r["status"]=="transit" or r["status"]=="delivered":return dict(r)
            if r["status"]!="requested":raise ValueError("Нельзя отправить отменённый груз")
            buyer=r["buyer"];sku=r["sku"];qty=r["qty"]
            total=qty*r["price"]
            freight=max(1000,total//50)
            if self.e._available_stock(owner,sku)<qty:raise ValueError("Недостаточно свободного товара")
            if self.e._available_cash(buyer)<total:raise ValueError("У покупателя недостаточно денег")
            if self.e._available_cash(owner)<freight:raise ValueError("Недостаточно денег для доставки")
            escrow="escrow:freight"
            if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner=?",(escrow,)).fetchone():
                self.e.create_company(escrow,r["origin"],0,"system")
            self.e._transfer("freight:hold:"+id,buyer,escrow,total)
            self.e._transfer("freight:fee:"+id,owner,self._treasury(r["origin"]),freight)
            cogs=self.e._consume(owner,sku,qty)
            self.e.db.execute("""UPDATE beta_freight SET status='transit',arriving_day=?,
input_cogs=?,freight_cost=? WHERE id=?""",(self.e.tick()+1,cogs,freight,id))
            return dict(self.e.db.execute("SELECT * FROM beta_freight WHERE id=?",(id,)).fetchone())

    def deliver_freight(self):
        delivered=0
        rows=self.e.db.execute("SELECT * FROM beta_freight WHERE status='transit' AND arriving_day<=? ORDER BY id",
            (self.e.tick(),)).fetchall()
        for r in rows:
            total=r["qty"]*r["price"]
            self.e._transfer("freight:release:"+r["id"],"escrow:freight",r["seller"],total)
            self.e._lot(r["buyer"],r["sku"],r["qty"],total)
            self.e.db.execute("UPDATE beta_freight SET status='delivered' WHERE id=?",(r["id"],))
            delivered+=1
        return delivered

    def retail(self,owner,bid,sku,qty,price,op):
        if type(qty)!=int or not 1<=qty<=20 or type(price)!=int or not 1<=price<=10**8:
            raise ValueError("Неверная розничная продажа")
        payload={"building_id":bid,"sku":sku,"qty":qty,"price":price}
        with self.e.atomic():
            cached=self._op(op,owner,"retail",payload)
            if cached is not None:return cached
            b=self._building(owner,bid)
            if b["enterprise_id"] not in SHOP_TYPES:raise ValueError("Это здание не магазин")
            if b["city"]!=self._company_city(owner):
                raise ValueError("Для торговли в другом городе нужна местная складская система")
            household="household:"+b["city"]
            if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner=?",(household,)).fetchone():
                raise ValueError("Население города пока не активировано")
            if sku not in self.e.goods:raise ValueError("Неизвестный товар")
            if self.e._available_stock(owner,sku)<qty:raise ValueError("Недостаточно свободного товара")
            if self.e.db.execute("SELECT 1 FROM city_demand WHERE city=? AND sku=? AND day=?",(b["city"],sku,self.e.tick())).fetchone() is None:
                self.e.set_demand(b["city"],sku,self.e.tick(),500000,20)
            result=self.e.household_purchase("beta:retail:"+op,b["city"],sku,owner,qty,price,household)
            return self._save(op,owner,"retail",payload,
                {"sold":qty,"sku":sku,"revenue":result["paid"],"gross_profit":result["seller_gross_profit"]})

    def history(self,owner):
        transfers=[dict(r) for r in self.e.db.execute("""
SELECT operation,source,destination,amount,tick FROM transfers
WHERE source=? OR destination=? ORDER BY id DESC LIMIT 40""",(owner,owner))]
        trades=[dict(r) for r in self.e.db.execute("""
SELECT sku,qty,price,tick,buyer,seller FROM trades
WHERE buyer=? OR seller=? ORDER BY id DESC LIMIT 40""",(owner,owner))]
        return {"transfers":transfers,"trades":trades,"tick":self.e.tick()}
