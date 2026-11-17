extends Control

# RussiaEconomicMMO: Android-first text economic beta.
# All actions are sent to the authoritative HTTPS server.
const BG = Color("#07131f")
const PANEL = Color("#122639")
const PANEL2 = Color("#1b3448")
const ACCENT = Color("#72e6c0")
const TEXT = Color("#f0f8fa")
const MUTED = Color("#acc3d0")
const AMBER = Color("#efc88c")
const BAD = Color("#e58f88")

var api_url := ""
var token := ""
var http: HTTPRequest
var pending := ""
var root_box: VBoxContainer
var title_label: Label
var info_label: Label
var username_input: LineEdit
var password_input: LineEdit
var url_input: LineEdit
var start_city := "Уфа"

var enterprises: Array = []
var cities: Array = []
var profile: Dictionary = {}
var goods_by_sku: Dictionary = {}
var market_data: Dictionary = {}
var world_data: Dictionary = {}
var ledger_data: Dictionary = {}
var contracts_data: Array = []
var shipments_data: Array = []
var directory_data: Array = []
var inventory_data: Array = []

var selected_enterprise: Dictionary = {}
var selected_building: Dictionary = {}
var selected_city := ""
var selected_size := 1
var chosen_x := -1
var chosen_y := -1
var map_data: Dictionary = {}
var recipe_data: Array = []
var source_data: Array = []
var current_building := 0
var selected_partner := ""
var filter_box: VBoxContainer

func _ready() -> void:
	RenderingServer.set_default_clear_color(BG)
	api_url = str(ProjectSettings.get_setting("application/config/api_url", ""))
	var prefs := ConfigFile.new()
	if prefs.load("user://settings.cfg") == OK:
		api_url = str(prefs.get_value("network", "api_url", api_url))
		token = str(prefs.get_value("network", "token", ""))
	http = HTTPRequest.new()
	http.timeout = 18.0
	add_child(http)
	http.request_completed.connect(_on_response)
	show_login()

func style_box(base: Color, radius: int = 16, border_color: Color = Color("#2b5060")) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = base
	box.set_corner_radius_all(radius)
	box.set_border_width_all(1)
	box.border_color = border_color
	box.content_margin_left = 12
	box.content_margin_right = 12
	box.content_margin_top = 9
	box.content_margin_bottom = 9
	return box

func reset_page(title: String) -> void:
	for child in get_children():
		if child != http:
			remove_child(child)
			child.queue_free()
	var backdrop := ColorRect.new()
	backdrop.color = BG
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(backdrop)
	move_child(backdrop, 0)
	var scroll := ScrollContainer.new()
	scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	add_child(scroll)
	var space := MarginContainer.new()
	space.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var left := 26
	var top := 18
	if OS.has_feature("mobile"):
		var safe_area := DisplayServer.get_display_safe_area()
		var real_screen := DisplayServer.screen_get_size()
		if real_screen.x > 0:
			left = maxi(left, int(float(safe_area.position.x) * 1280.0 / float(real_screen.x)) + 12)
		if real_screen.y > 0:
			top = maxi(top, int(float(safe_area.position.y) * 720.0 / float(real_screen.y)) + 10)
	space.add_theme_constant_override("margin_left", left)
	space.add_theme_constant_override("margin_right", left)
	space.add_theme_constant_override("margin_top", top)
	space.add_theme_constant_override("margin_bottom", top)
	scroll.add_child(space)
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", style_box(Color("#102235e8"), 24, Color("#355a69")))
	space.add_child(panel)
	var inner := MarginContainer.new()
	inner.add_theme_constant_override("margin_left", 17)
	inner.add_theme_constant_override("margin_right", 17)
	inner.add_theme_constant_override("margin_top", 15)
	inner.add_theme_constant_override("margin_bottom", 17)
	panel.add_child(inner)
	root_box = VBoxContainer.new()
	root_box.add_theme_constant_override("separation", 11)
	inner.add_child(root_box)
	var ribbon := HBoxContainer.new()
	root_box.add_child(ribbon)
	var brand := Label.new()
	brand.text = "◈  RUSSIA ECONOMIC MMO"
	brand.add_theme_color_override("font_color", ACCENT)
	brand.add_theme_font_size_override("font_size", 14)
	ribbon.add_child(brand)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ribbon.add_child(spacer)
	var version := Label.new()
	version.text = "BETA 0.2   •   " + ("ONLINE" if token != "" else "ANDROID")
	version.add_theme_color_override("font_color", MUTED)
	version.add_theme_font_size_override("font_size", 14)
	ribbon.add_child(version)
	title_label = Label.new()
	title_label.text = title
	title_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title_label.add_theme_color_override("font_color", TEXT)
	title_label.add_theme_font_size_override("font_size", 31)
	root_box.add_child(title_label)
	info_label = Label.new()
	info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	info_label.add_theme_color_override("font_color", AMBER)
	info_label.add_theme_font_size_override("font_size", 16)
	info_label.text = ""
	root_box.add_child(info_label)

func label(text: String, size: int = 19, tone: Color = TEXT) -> Label:
	var output := Label.new()
	output.text = text
	output.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	output.add_theme_color_override("font_color", tone)
	output.add_theme_font_size_override("font_size", size)
	root_box.add_child(output)
	return output

func section(text: String) -> void:
	var title := label(text, 21, ACCENT)
	title.add_theme_constant_override("outline_size", 1)

func button(text: String, cb: Callable, parent: Container = null) -> Button:
	var item := Button.new()
	item.text = text
	item.custom_minimum_size = Vector2(0, 54)
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item.add_theme_font_size_override("font_size", 17)
	item.add_theme_color_override("font_color", TEXT)
	item.add_theme_color_override("font_hover_color", ACCENT)
	item.add_theme_stylebox_override("normal", style_box(PANEL2, 15))
	item.add_theme_stylebox_override("hover", style_box(Color("#264d56"), 15, ACCENT))
	item.add_theme_stylebox_override("pressed", style_box(Color("#225b50"), 15, ACCENT))
	item.add_theme_stylebox_override("focus", style_box(Color("#193d44"), 15, ACCENT))
	item.pressed.connect(cb)
	if parent:
		parent.add_child(item)
	else:
		root_box.add_child(item)
	return item

func input(placeholder: String, secret: bool = false) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.secret = secret
	e.custom_minimum_size = Vector2(0, 56)
	e.add_theme_font_size_override("font_size", 19)
	e.add_theme_color_override("font_color", TEXT)
	e.add_theme_stylebox_override("normal", style_box(PANEL2, 14))
	e.add_theme_stylebox_override("focus", style_box(Color("#25475a"), 14, ACCENT))
	root_box.add_child(e)
	return e

func op(prefix: String) -> String:
	return prefix + ":" + str(Time.get_ticks_usec()) + ":" + str(randi())

func money(kopecks: int) -> String:
	return "%.2f ₽" % (float(kopecks) / 100.0)

func parse_rubles(value: String) -> int:
	var clean := value.strip_edges().replace(",", ".")
	var halves := clean.split(".")
	if halves.size() < 1 or halves.size() > 2 or not halves[0].is_valid_int():
		return -1
	if halves[0].begins_with("-"):
		return -1
	var kop := 0
	if halves.size() == 2:
		if halves[1].length() > 2 or not halves[1].is_valid_int():
			return -1
		kop = int(halves[1].rpad(2, "0"))
	return int(halves[0]) * 100 + kop

func known_name(sku: String) -> String:
	var row: Dictionary = goods_by_sku.get(sku, {})
	return str(row.get("name", sku))

func save_settings() -> void:
	var prefs := ConfigFile.new()
	prefs.set_value("network", "api_url", api_url)
	prefs.set_value("network", "token", token)
	prefs.save("user://settings.cfg")

func request_api(method: String, path: String, body: Dictionary, response_mode: String) -> void:
	if http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		info_label.text = "Загрузка... попробуйте ещё раз после завершения запроса."
		return
	if not api_url.begins_with("https://") and not api_url.begins_with("http://"):
		info_label.text = "Укажите адрес сервера."
		return
	pending = response_mode
	var headers := PackedStringArray(["Content-Type: application/json"])
	if token != "":
		headers.append("Authorization: Bearer " + token)
	var payload := JSON.stringify(body) if method == "POST" else ""
	var status := http.request(api_url + path, headers, HTTPClient.METHOD_POST if method == "POST" else HTTPClient.METHOD_GET, payload)
	if status != OK:
		info_label.text = "Ошибка подключения: " + str(status)

func _on_response(result: int, code: int, _headers: PackedStringArray, payload: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		info_label.text = "Нет связи с сервером: " + str(result)
		return
	var parsed = JSON.parse_string(payload.get_string_from_utf8())
	if not parsed is Dictionary:
		info_label.text = "Ответ сервера не удалось прочитать."
		return
	if code >= 400:
		info_label.text = str(parsed.get("error", "Ошибка сервера, код " + str(code)))
		return
	match pending:
		"auth":
			token = str(parsed.get("token", ""))
			save_settings()
			request_api("GET", "/api/profile", {}, "profile")
		"profile":
			profile = parsed
			show_home()
			if goods_by_sku.is_empty():
				request_api("GET", "/api/goods", {}, "goods")
		"goods":
			for item in parsed.get("goods", []):
				goods_by_sku[str(item.get("sku", ""))] = item
			show_home()
		"catalog":
			enterprises = parsed.get("enterprises", [])
			cities = parsed.get("cities", [])
			show_catalog()
		"map":
			map_data = parsed
			chosen_x = -1
			chosen_y = -1
			show_map()
		"inventory":
			inventory_data = parsed.get("inventory", [])
			show_inventory()
		"recipes":
			recipe_data = parsed.get("recipes", [])
			request_api("GET", "/api/sources?building_id=" + str(current_building), {}, "sources")
		"sources":
			source_data = parsed.get("goods", [])
			show_building()
		"market":
			market_data = parsed
			show_market()
		"world":
			world_data = parsed
			show_world()
		"ledger":
			ledger_data = parsed
			show_ledger()
		"contracts":
			contracts_data = parsed.get("contracts", [])
			show_contracts()
		"shipments":
			shipments_data = parsed.get("shipments", [])
			show_shipments()
		"directory":
			directory_data = parsed.get("companies", [])
			show_directory()
		"imported", "harvested":
			request_api("GET", "/api/inventory", {}, "inventory")
		"built", "upgraded", "produced", "auto_changed":
			request_api("GET", "/api/profile", {}, "profile")
		"ordered", "order_cancelled":
			request_api("GET", "/api/book", {}, "market")
		"contract_created", "contract_done":
			request_api("GET", "/api/contracts", {}, "contracts")
		"freight_created", "freight_accepted":
			request_api("GET", "/api/shipments", {}, "shipments")
		"retail_done":
			request_api("GET", "/api/profile", {}, "profile")

func show_login() -> void:
	reset_page("РОССИЯ: ЭКОНОМИЧЕСКАЯ ИМПЕРИЯ")
	label("Настоящие конкуренты, производство и города России. Первая текстовая онлайн-версия.", 19, MUTED)
	url_input = input("HTTPS-адрес игрового сервера")
	url_input.text = api_url
	username_input = input("Логин")
	password_input = input("Пароль, от 8 символов", true)
	label("Стартовый город для новой компании:", 15, MUTED)
	var starter := OptionButton.new()
	var options := ["Уфа","Москва","Санкт-Петербург","Казань","Екатеринбург",
		"Новосибирск","Краснодар","Ростов-на-Дону","Самара","Владивосток"]
	for c in options:
		starter.add_item(c)
	starter.custom_minimum_size = Vector2(0, 54)
	root_box.add_child(starter)
	starter.item_selected.connect(func(index: int): start_city = options[index])
	button("Войти в компанию", func(): authenticate(false))
	button("Создать новую компанию", func(): authenticate(true))
	if token != "":
		button("Продолжить сохранённую сессию", func(): request_api("GET", "/api/profile", {}, "profile"))
	label("Ваш прогресс хранится на сервере. Текстовая карта используется только при строительстве.", 15, MUTED)

func authenticate(new_account: bool) -> void:
	api_url = url_input.text.strip_edges().trim_suffix("/")
	if not api_url.begins_with("https://") and not api_url.begins_with("http://"):
		info_label.text = "Введите адрес HTTPS-сервера."
		return
	if username_input.text.strip_edges().length() < 3 or password_input.text.length() < 8:
		info_label.text = "Логин от 3 символов, пароль от 8."
		return
	save_settings()
	request_api("POST", "/api/register" if new_account else "/api/login",
		{"username": username_input.text.strip_edges(), "password": password_input.text,
		"city": start_city}, "auth")

func show_home() -> void:
	reset_page("МОЯ КОМПАНИЯ")
	section("ФИНАНСЫ И АКТИВЫ")
	label("Капитал     " + money(int(profile.get("cash", 0))), 27, ACCENT)
	label("Доступно     " + money(int(profile.get("available_cash", profile.get("cash", 0)))) +
		"     •     Предприятий: " + str(profile.get("buildings", []).size()), 19)
	label("Город штаб-квартиры: " + str(profile.get("city", "Уфа")) +
		"     •     Игровые сутки: " + str(profile.get("tick", 0)), 16, MUTED)
	section("УПРАВЛЕНИЕ")
	button("＋  Строительство и недвижимость", func(): request_api("GET", "/api/catalog", {}, "catalog"))
	button("▤  Предприятия, производство, улучшения", show_owned)
	button("▣  Склады и закупка сырья", func(): request_api("GET", "/api/inventory", {}, "inventory"))
	button("≋  Биржа и торговые заявки", func(): request_api("GET", "/api/book", {}, "market"))
	button("◇  Контракты с другими компаниями", func(): request_api("GET", "/api/contracts", {}, "contracts"))
	button("▥  Доставка между городами", func(): request_api("GET", "/api/shipments", {}, "shipments"))
	button("♜  Компании и конкуренты", func(): request_api("GET", "/api/companies", {}, "directory"))
	button("◷  Игровой мир и календарь", func(): request_api("GET", "/api/world", {}, "world"))
	button("▤  Финансовые операции", func(): request_api("GET", "/api/ledger", {}, "ledger"))
	button("↻  Обновить данные", func(): request_api("GET", "/api/profile", {}, "profile"))
	button("Выйти из аккаунта", func():
		token = ""
		save_settings()
		show_login()
	)

func show_owned() -> void:
	reset_page("МОИ ПРЕДПРИЯТИЯ")
	button("← Главная", show_home)
	var own: Array = profile.get("buildings", [])
	if own.is_empty():
		label("Пока нет построек. Откройте каталог и выберите первое предприятие.", 18, MUTED)
	for item in own:
		var b: Dictionary = item
		button("▣ " + str(b.get("enterprise_id", "")) +
			"  •  " + str(b.get("city", "")) +
			"  •  " + str(b.get("size", 1)) + "×" + str(b.get("size", 1)) +
			"  •  ур. " + str(b.get("level", 1)), func(): open_building(b))

func show_catalog() -> void:
	reset_page("КАТАЛОГ СТРОИТЕЛЬСТВА")
	button("← Главная", show_home)
	label("Выберите здание: сначала описание, потом город и только затем карта размещения.", 17, MUTED)
	var filter := input("Поиск: магазин, ферма, завод, склад...")
	filter_box = VBoxContainer.new()
	filter_box.add_theme_constant_override("separation", 9)
	root_box.add_child(filter_box)
	filter.text_changed.connect(func(value): render_catalog(value))
	render_catalog("")

func render_catalog(query: String) -> void:
	for child in filter_box.get_children():
		filter_box.remove_child(child)
		child.queue_free()
	var query_l := query.to_lower().strip_edges()
	var shown := 0
	for item in enterprises:
		var entry: Dictionary = item
		var name := str(entry.get("name", entry.get("id", "")))
		var category := str(entry.get("category", ""))
		if query_l != "" and not (name.to_lower().contains(query_l) or
			category.to_lower().contains(query_l) or str(entry.get("id","")).to_lower().contains(query_l)):
			continue
		shown += 1
		button(name + "   •   " + money(int(entry.get("cost", 0))) +
			"   •   " + category, func(): show_enterprise(entry), filter_box)
	if shown == 0:
		button("Ничего не найдено: очистить поиск", func(): show_catalog(), filter_box)

func show_enterprise(entry: Dictionary) -> void:
	selected_enterprise = entry
	selected_size = 1
	reset_page(str(entry.get("name", entry.get("id", ""))))
	button("← Вернуться к каталогу", show_catalog)
	section(str(entry.get("category", "Предприятие")))
	label("Код: " + str(entry.get("id", "")), 16, MUTED)
	label("Производственных рецептов: " + str(entry.get("recipe_count", 0)), 18)
	label("Доступных сырьевых продуктов: " + str(entry.get("source_count", 0)), 18)
	label("Возможности: строительство, улучшение, управление запасами и производством.", 16, MUTED)
	section("РАЗМЕР УЧАСТКА")
	var select := OptionButton.new()
	for n in [1, 2, 3]:
		select.add_item(str(n) + "×" + str(n))
	select.custom_minimum_size = Vector2(0, 54)
	root_box.add_child(select)
	var cost_label := label("Стоимость: " + money(int(entry.get("cost", 0))), 22, ACCENT)
	select.item_selected.connect(func(index: int):
		selected_size = index + 1
		cost_label.text = "Стоимость: " + money(int(entry.get("cost", 0)) * selected_size * selected_size)
	)
	button("Строить → Выбрать город", show_cities)

func show_cities() -> void:
	reset_page("ГОРОД СТРОИТЕЛЬСТВА")
	button("← Карточка здания", func(): show_enterprise(selected_enterprise))
	var favorites: Array = []
	for b in profile.get("buildings", []):
		var name := str(b.get("city",""))
		if not favorites.has(name):
			favorites.append(name)
	var ordered: Array = []
	for city in cities:
		if favorites.has(city):
			ordered.append(city)
	for city in cities:
		if not favorites.has(city):
			ordered.append(city)
	label("Города с вашими предприятиями показаны первыми.", 17, MUTED)
	for c in ordered:
		var place := str(c)
		button(("★ " if favorites.has(place) else "") + place, func():
			selected_city = place
			request_api("GET", "/api/map?city=" + place.uri_encode(), {}, "map")
		)

func tile_available(x: int, y: int) -> bool:
	if x + selected_size > int(map_data.get("width",24)) or y + selected_size > int(map_data.get("height",16)):
		return false
	for b in map_data.get("buildings", []):
		var bx := int(b.get("x",0))
		var by := int(b.get("y",0))
		var bs := int(b.get("size",1))
		if x < bx + bs and x + selected_size > bx and y < by + bs and y + selected_size > by:
			return false
	return true

func show_map() -> void:
	reset_page("УЧАСТКИ  •  " + selected_city)
	button("← Выбор города", show_cities)
	label("Коснитесь свободного участка. Клетки занятых зданий не доступны.", 16, MUTED)
	label("Объект: " + str(selected_enterprise.get("name","")) +
		"  •  Размер: " + str(selected_size) + "×" + str(selected_size), 17, ACCENT)
	var occupied: Dictionary = {}
	for b in map_data.get("buildings", []):
		var px := int(b.get("x",0))
		var py := int(b.get("y",0))
		for oy in range(int(b.get("size",1))):
			for ox in range(int(b.get("size",1))):
				occupied[str(px+ox) + ":" + str(py+oy)] = b
	var board := GridContainer.new()
	board.columns = int(map_data.get("width",24))
	board.add_theme_constant_override("h_separation", 3)
	board.add_theme_constant_override("v_separation", 3)
	root_box.add_child(board)
	for y in range(int(map_data.get("height",16))):
		for x in range(int(map_data.get("width",24))):
			var cx := x
			var cy := y
			var place := str(x) + ":" + str(y)
			var tile := Button.new()
			tile.custom_minimum_size = Vector2(31, 28)
			tile.text = "■" if occupied.has(place) else "·"
			var mine := occupied.has(place) and str(occupied[place].get("owner","")) == str(profile.get("owner",""))
			tile.add_theme_font_size_override("font_size", 13)
			if occupied.has(place):
				tile.modulate = ACCENT if mine else AMBER
				tile.disabled = true
			elif chosen_x >= 0 and x >= chosen_x and x < chosen_x+selected_size and y >= chosen_y and y < chosen_y+selected_size:
				tile.modulate = ACCENT
			else:
				tile.modulate = Color("#afc5d0")
			tile.pressed.connect(func(): choose_plot(cx, cy))
			board.add_child(tile)
	if chosen_x >= 0:
		label("Ваш участок: " + str(chosen_x) + ", " + str(chosen_y) +
			"   •   К оплате: " +
			money(int(selected_enterprise.get("cost",0)) * selected_size * selected_size), 19, ACCENT)
		button("Построить на выбранном месте", func():
			request_api("POST", "/api/build", {
				"operation": op("build"), "enterprise_id": selected_enterprise.get("id", ""),
				"city": selected_city, "x": chosen_x, "y": chosen_y, "size": selected_size
			}, "built")
		)

func choose_plot(x: int, y: int) -> void:
	if not tile_available(x,y):
		info_label.text = "Не хватает свободных клеток под выбранный размер."
		return
	chosen_x=x
	chosen_y=y
	show_map()

func open_building(b: Dictionary) -> void:
	selected_building=b
	current_building=int(b.get("id",0))
	request_api("GET", "/api/recipes?building_id=" + str(current_building), {}, "recipes")

func show_building() -> void:
	reset_page("УПРАВЛЕНИЕ ЗДАНИЕМ")
	button("← Мои предприятия", show_owned)
	section(str(selected_building.get("enterprise_id","")) + "  •  " + str(selected_building.get("city","")))
	label("Уровень: " + str(selected_building.get("level",1)) +
		"   •   Размер " + str(selected_building.get("size",1)) + "×" + str(selected_building.get("size",1)))
	button("↑ Улучшить здание", func():
		request_api("POST", "/api/upgrade", {
			"operation": op("upgrade"), "building_id": current_building
		}, "upgraded")
	)
	if not source_data.is_empty():
		section("ДОБЫЧА / СЕЛЬСКОЕ ХОЗЯЙСТВО")
		for raw in source_data:
			label(str(raw.get("sku","")) + " • " + str(raw.get("name","")) +
				"   •   Запас: " + str(raw.get("remaining",0)), 16, MUTED)
		var source_sku := input("Артикул сырья, например AGRI-001")
		var source_qty := input("Количество для добычи")
		button("Произвести сырьё", func():
			if not source_qty.text.is_valid_int():
				info_label.text = "Введите целое количество."
				return
			request_api("POST", "/api/harvest", {
				"operation": op("harvest"), "building_id": current_building,
				"sku": source_sku.text.strip_edges().to_upper(), "qty": int(source_qty.text)
			}, "harvested")
		)
	if not recipe_data.is_empty():
		section("ПРОИЗВОДСТВО")
		label("Выберите рецепт. Сырьё должно быть на вашем складе.", 16, MUTED)
		for rec in recipe_data:
			var r: Dictionary=rec
			var inputs: Array = []
			for i in r.get("inputs", []):
				inputs.append(str(i.get("goods_id","")) + " × " + str(i.get("quantity",0)))
			label(str(r.get("goods_id","")) + "  •  " + known_name(str(r.get("goods_id",""))), 18, ACCENT)
			label("Рецепт " + str(r.get("id","")) + "     Сырьё: " + ", ".join(inputs), 14, MUTED)
			button("▶ Выпустить партию", func():
				request_api("POST", "/api/produce", {
					"operation": op("prod"), "building_id": current_building,
					"recipe_id": r.get("id","")
				}, "produced")
			)
			button("◴ Автоматизировать этот рецепт", func():
				request_api("POST", "/api/automation", {
					"operation": op("auto"), "building_id": current_building,
					"recipe_id": r.get("id",""), "enabled": true
				}, "auto_changed")
			)
	elif source_data.is_empty():
		label("Здание построено. Для этого типа пока нет непосредственных производственных рецептов.", 16, MUTED)
	if str(selected_building.get("enterprise_id","")) in ["ENT-041","ENT-042","ENT-043"]:
		section("РОЗНИЧНАЯ ТОРГОВЛЯ")
		button("Продать населению со склада", show_retail)
	button("Склад и закупка сырья", func(): request_api("GET", "/api/inventory", {}, "inventory"))

func show_inventory() -> void:
	reset_page("СКЛАД И ЗАКУПКИ")
	button("← Главная", show_home)
	section("ТОВАРНЫЕ ОСТАТКИ")
	if inventory_data.is_empty():
		label("На складе пока пусто.", 17, MUTED)
	for item in inventory_data:
		label(str(item.get("goods_id","")) + "  •  " + known_name(str(item.get("goods_id",""))) +
			"   × " + str(item.get("qty",0)), 16)
	section("ИМПОРТ СЫРЬЯ")
	label("Покупка ограниченного количества ресурсов у системного поставщика.", 15, MUTED)
	var sku := input("Артикул, например AGRI-001")
	var qty := input("Количество, не более 5000")
	button("Закупить сырьё", func():
		if not qty.text.is_valid_int():
			info_label.text = "Количество должно быть целым числом."
			return
		request_api("POST", "/api/import", {
			"operation": op("import"), "sku": sku.text.strip_edges().to_upper(), "qty": int(qty.text)
		}, "imported")
	)

func show_market() -> void:
	reset_page("БИРЖА  •  " + str(market_data.get("city","")))
	button("← Главная", show_home)
	section("ВЫСТАВИТЬ ЗАЯВКУ")
	label("Товар и количество фиксируются. Биржа автоматически сопоставляет цены.", 16, MUTED)
	var sku := input("Артикул товара")
	var qty := input("Количество")
	var rub := input("Цена за единицу, ₽")
	button("Купить", func(): place_market("buy",sku,qty,rub))
	button("Продать", func(): place_market("sell",sku,qty,rub))
	section("МОИ ЗАЯВКИ")
	for r in market_data.get("mine", []):
		var order_row: Dictionary = r
		label(str(order_row.get("side","")) + " • " + str(order_row.get("sku","")) +
			" • " + str(order_row.get("qty_left",0)) + " ед. • " +
			money(int(order_row.get("price",0))) + " • " + str(order_row.get("status","")), 16, MUTED)
		if str(order_row.get("status",""))=="open":
			button("Отменить " + str(order_row.get("id","")),func():
				request_api("POST", "/api/order/cancel",
					{"order_id":order_row.get("id","")}, "order_cancelled")
			)
	section("АКТИВНЫЕ ПРЕДЛОЖЕНИЯ")
	for r in market_data.get("orders", []):
		label(str(r.get("side","")) + "   " + str(r.get("sku","")) + "  × " +
			str(r.get("qty_left",0)) + "   " + money(int(r.get("price",0))), 15)

func place_market(side: String, sku: LineEdit, qty: LineEdit, rub: LineEdit) -> void:
	if not qty.text.is_valid_int() or parse_rubles(rub.text) <= 0:
		info_label.text = "Укажите количество и цену (в рублях)."
		return
	request_api("POST","/api/order",{
		"operation":op("market"),"side":side,"sku":sku.text.strip_edges().to_upper(),
		"qty":int(qty.text),"price":parse_rubles(rub.text)
	},"ordered")

func show_directory() -> void:
	reset_page("КОМПАНИИ И КОНКУРЕНТЫ")
	button("← Главная",show_home)
	label("Выберите контрагента. Сделки внутри города оформляются контрактом, между городами доставкой.", 16, MUTED)
	var search := input("Поиск компании")
	var results := VBoxContainer.new()
	root_box.add_child(results)
	var populate := func(query: String):
		for c in results.get_children():
			results.remove_child(c)
			c.queue_free()
		var count := 0
		for comp in directory_data:
			var row: Dictionary=comp
			var cid := str(row.get("id",""))
			if query.strip_edges() != "" and not cid.to_lower().contains(query.to_lower()):
				continue
			if cid == str(profile.get("owner","")): continue
			count += 1
			if count > 35:break
			button(cid + " • " + str(row.get("city","")),func():
				selected_partner=cid
				if str(row.get("city",""))==str(profile.get("city","")):
					request_api("GET", "/api/contracts", {}, "contracts")
				else:
					request_api("GET", "/api/shipments", {}, "shipments")
			,results)
	populate.call("")
	search.text_changed.connect(populate)

func show_contracts() -> void:
	reset_page("ТОРГОВЫЕ КОНТРАКТЫ")
	button("← Главная",show_home)
	label("Договор между компаниями одного города. Покупатель оформляет запрос, поставщик исполняет.", 16, MUTED)
	var seller := input("ID компании-поставщика")
	seller.text = selected_partner
	var sku := input("Артикул товара")
	var qty := input("Количество")
	var price := input("Цена за единицу, ₽")
	button("Создать контракт", func():
		if not qty.text.is_valid_int() or parse_rubles(price.text) <= 0:
			info_label.text = "Проверьте количество и цену."
			return
		request_api("POST", "/api/contract", {
			"operation":op("contract"),"seller":seller.text.strip_edges(),
			"sku":sku.text.strip_edges().to_upper(),"qty":int(qty.text),
			"price":parse_rubles(price.text)
		},"contract_created")
	)
	section("ДОГОВОРЫ")
	for contract in contracts_data:
		var c: Dictionary=contract
		label(str(c.get("id","")) + "   •   " + str(c.get("goods_id","")) +
			" × " + str(c.get("qty",0)) + "  •  " + str(c.get("status","")), 16)
		if str(c.get("seller",""))==str(profile.get("owner","")) and str(c.get("status",""))=="open":
			button("Исполнить контракт", func():
				request_api("POST","/api/contract/fulfill",
					{"contract_id":c.get("id","")},"contract_done")
			)

func show_shipments() -> void:
	reset_page("МЕЖГОРОДСКАЯ ДОСТАВКА")
	button("← Главная",show_home)
	label("Покупатель заказывает товар у компании в другом городе. Отгрузка происходит после согласия продавца; груз прибывает через игровые сутки.", 16, MUTED)
	var seller := input("ID компании-продавца")
	seller.text = selected_partner
	var sku := input("Артикул товара")
	var qty := input("Количество")
	var price := input("Цена за единицу, ₽")
	button("Заказать доставку",func():
		if not qty.text.is_valid_int() or parse_rubles(price.text)<=0:
			info_label.text = "Проверьте количество и цену."
			return
		request_api("POST","/api/freight",{
			"operation":op("freight"),"seller":seller.text.strip_edges(),
			"sku":sku.text.strip_edges().to_upper(),"qty":int(qty.text),
			"price":parse_rubles(price.text)
		},"freight_created")
	)
	section("МОИ ПЕРЕВОЗКИ")
	for item in shipments_data:
		var f: Dictionary=item
		label(str(f.get("sku","")) + " × " + str(f.get("qty",0)) +
			" • " + str(f.get("origin","")) + " → " + str(f.get("destination","")) +
			" • " + str(f.get("status","")), 16)
		if str(f.get("seller",""))==str(profile.get("owner","")) and str(f.get("status",""))=="requested":
			button("Принять и отправить",func():
				request_api("POST","/api/freight/accept",
					{"shipment_id":f.get("id","")},"freight_accepted")
			)

func show_retail() -> void:
	reset_page("РОЗНИЧНЫЕ ПРОДАЖИ")
	button("← Управление магазином",show_building)
	label("Продажа товаров из склада местному населению. Покупка возможна, только если есть спрос и бюджет.", 16, MUTED)
	var sku := input("Артикул товара")
	var qty := input("Количество, 1–20")
	var price := input("Цена за единицу, ₽")
	button("Предложить населению",func():
		if not qty.text.is_valid_int() or parse_rubles(price.text)<=0:
			info_label.text = "Проверьте количество и цену."
			return
		request_api("POST","/api/retail",{
			"operation":op("retail"),"building_id":current_building,
			"sku":sku.text.strip_edges().to_upper(),"qty":int(qty.text),
			"price":parse_rubles(price.text)
		},"retail_done")
	)

func show_world() -> void:
	reset_page("МИР И КАЛЕНДАРЬ")
	button("← Главная",show_home)
	label("Общий серверный мир России", 20, ACCENT)
	label("Игровой год: " + str(world_data.get("year",1)) +
		"  •  День года: " + str(world_data.get("day_of_year",1)), 23)
	label("7 реальных дней = 1 игровой год (365 игровых суток).", 17, MUTED)
	label("ИИ-компаний: " + str(world_data.get("ai_companies",0)), 19)
	label("Общая денежная масса: " + money(int(world_data.get("money_supply_kopecks",0))), 18)
	var last: Dictionary=world_data.get("last_report",{}) if world_data.get("last_report",null) is Dictionary else {}
	if not last.is_empty():
		section("ПОСЛЕДНИЕ ИГРОВЫЕ СУТКИ")
		label("Сделок: " + str(last.get("trades",0)) +
			"  •  Действий ИИ: " + str(last.get("ai_decisions",0)), 18)
	button("↻ Обновить календарь",func(): request_api("GET","/api/world",{},"world"))

func show_ledger() -> void:
	reset_page("ФИНАНСОВЫЙ ЖУРНАЛ")
	button("← Главная",show_home)
	section("ДЕНЕЖНЫЕ ОПЕРАЦИИ")
	for entry in ledger_data.get("transfers", []):
		var src := str(entry.get("source",""))
		var sign := "−" if src == str(profile.get("owner","")) else "+"
		label(sign + money(int(entry.get("amount",0))) + "   •   " +
			str(entry.get("operation","")) + "   •   день " + str(entry.get("tick",0)), 15)
	section("ЗАКЛЮЧЁННЫЕ БИРЖЕВЫЕ СДЕЛКИ")
	for trade in ledger_data.get("trades", []):
		label(str(trade.get("sku","")) + " × " + str(trade.get("qty",0)) +
			"  по " + money(int(trade.get("price",0))), 16)
