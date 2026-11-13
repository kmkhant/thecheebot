"""Translations for every string the bot says.

Burmese is the default; English and Chinese are opt-in, either through the
Telegram client's language or with /language. Copy lives here rather than in
``texts`` so the formatting logic stays free of prose.

Every catalogue must define the same keys with the same ``{}`` placeholders —
``tests/test_i18n.py`` enforces both.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "my"

# Ordered as they appear in the language picker: default first, then English.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("my", "en", "zh")

LANGUAGE_NAMES: dict[str, str] = {
    "my": "မြန်မာ",
    "en": "English",
    "zh": "中文",
}

# Telegram reports a locale tag such as "en-US" or "zh-Hans"; only the primary
# subtag matters here.
_ALIASES: dict[str, str] = {
    "my": "my",
    "mm": "my",
    "bur": "my",
    "en": "en",
    "eng": "en",
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    "cmn": "zh",
}


def normalize_language(code: str | None) -> str | None:
    """Map a client locale to a supported language, or None if there isn't one."""
    if not code:
        return None
    primary = code.strip().lower().replace("_", "-").split("-")[0]
    return _ALIASES.get(primary)


def language_name(code: str) -> str:
    """The language's own name, shown in the picker regardless of the UI language."""
    return LANGUAGE_NAMES.get(code, code)


def t(lang: str, key: str, **values: object) -> str:
    """Look ``key`` up in ``lang``'s catalogue and fill in placeholders.

    An unsupported language falls back to Burmese, so a stale stored preference
    can never produce a KeyError in a handler.
    """
    catalog = MESSAGES.get(lang) or MESSAGES[DEFAULT_LANGUAGE]
    template = catalog[key]
    return template.format(**values) if values else template


_MY: dict[str, str] = {
    # Menu and buttons
    "menu_nearest": "📍 အနီးဆုံး",
    "menu_share": "➕ မျှဝေ",
    "menu_find": "🔍 ရှာဖွေ",
    "menu_mine": "📋 ကျွန်ုပ်၏ နေရာများ",
    "menu_about": "ℹ️ အကြောင်း",
    "menu_cancel": "✖️ ပယ်ဖျက်",
    "menu_skip": "⏭ ကျော်",
    "menu_language": "🌐 ဘာသာစကား",
    "btn_directions": "🗺 လမ်းညွှန်",
    "btn_share": "🔗 မျှဝေ",
    "btn_report": "🚩 အစီရင်ခံ",
    "btn_same_place": "✅ ဒီနေရာပဲ",
    "btn_different_place": "🆕 မတူဘူး",
    "btn_rename": "✏️ အမည်ပြောင်း",
    "btn_delete": "🗑 ဖျက်",
    "btn_delete_yes": "✅ ဖျက်မည်",
    "btn_delete_no": "✖️ မဖျက်တော့",
    # Onboarding
    "welcome": (
        "👋 <b>cheebot မှ ကြိုဆိုပါသည်</b>\n\n"
        "သင့်အနီးရှိ အိမ်သာကို ရှာပါ၊ အခြားသူများလည်း ရှာတွေ့အောင် ကူညီပါ။ "
        "အခမဲ့၊ အကောင့်မလို၊ ကြော်ငြာမရှိ။\n\n"
        "📍 <b>အနီးဆုံး</b> — တည်နေရာပို့ပြီး အနီးဆုံး အိမ်သာများကို ကြည့်ပါ\n"
        "➕ <b>မျှဝေ</b> — သင်သိသော နေရာတစ်ခု ထည့်ပါ\n"
        "🔍 <b>ရှာဖွေ</b> — အမည် သို့မဟုတ် ဧရိယာအလိုက် ရှာပါ"
    ),
    "welcome_inline": (
        "<b>မည်သည့် ချက်တင်တွင်မဆို</b> <code>@{username}</code> ရိုက်ပြီး "
        "နောက်တွင် နေရာအမည် ထည့်ပါက ထိုနေရာရှိ အိမ်သာကို မျှဝေနိုင်သည်။"
    ),
    "welcome_footer": "စတင်ရန် အောက်ပါ ခလုတ်တစ်ခုကို နှိပ်ပါ။",
    "help": (
        "<b>cheebot ကို ဘယ်လိုသုံးမလဲ</b>\n\n"
        "/nearest — သင့်အနီးဆုံး အိမ်သာများ\n"
        "/share — မြေပုံပေါ်သို့ အိမ်သာတစ်ခု ထည့်ရန်\n"
        "/find &lt;အမည် သို့မဟုတ် ဧရိယာ&gt; — စာသားဖြင့် ရှာရန်\n"
        "/mine — သင်ထည့်ထားသော နေရာများကို စီမံရန်\n"
        "/about — ဒေတာ ဘယ်ကလာသလဲ\n"
        "/language — ဘာသာစကား ပြောင်းရန်\n"
        "/cancel — လုပ်ဆောင်နေသည်ကို ရပ်ရန်"
    ),
    "help_inline": (
        "<b>မည်သည့် ချက်တင်တွင်မဆို</b>: <code>@{username}</code> နှင့် နေရာအမည်၊ "
        "ဥပမာ <code>@{username} ဗိုလ်ချုပ်လမ်း</code>။"
    ),
    "about": (
        "<b>cheebot အကြောင်း</b>\n\n"
        "cheebot သည် အခမဲ့ဖြစ်သည် — ကြော်ငြာမရှိ၊ အကောင့်မလို၊ ခြေရာခံမှုမရှိ။\n\n"
        "<b>ဒေတာ ဘယ်ကလာသလဲ</b>\n"
        "နေရာများကို သင့်ကဲ့သို့ လူများက ထည့်သည်။ ထို့အပြင် OpenStreetMap မှ "
        "အများသုံး မြေပုံဒေတာကိုလည်း သုံးသည်။ Map data © OpenStreetMap "
        "contributors၊ Open Database License (ODbL) အောက်တွင် ရရှိနိုင်သည်။\n"
        "https://www.openstreetmap.org/copyright\n\n"
        "<b>ကိုယ်ရေးကိုယ်တာ</b>\n"
        "သင်ပို့သော တည်နေရာကို ထို ရှာဖွေမှုအတွက်သာ တစ်ကြိမ် သုံးပြီး မသိမ်းဆည်းပါ။ "
        "ထည့်သွင်းမှုများတွင် စပမ်းတားရန် သင့်အကောင့် id ကို ဆားရောစပ် hash "
        "ပြုထားသည်ကိုသာ သိမ်းသည် — သင့် id၊ အမည် သို့မဟုတ် ဖုန်းနံပါတ်ကို "
        "မဟုတ်ပါ။\n\n"
        "တစ်ခုခု မှားနေသလား သို့မဟုတ် လိုနေသလား။ ရလဒ်တိုင်းတွင် 🚩 အစီရင်ခံ ကို "
        "နှိပ်ပါ၊ သို့မဟုတ် 1–5 ကြယ် ပေးပါ။\n\n"
        "🌐 ဘာသာစကား ကို နှိပ်ပြီး မြန်မာ၊ English၊ 中文 ကို ပြောင်းနိုင်သည်။"
    ),
    # Nearest
    "ask_location_nearest": (
        "သင့်တည်နေရာကို ပို့ပါ၊ အနီးဆုံး အိမ်သာများကို စာရင်းပြပါမည်။ "
        "အခြားနေရာမှ ရှာလိုပါက မြေပုံလင့်ခ် သို့မဟုတ် ကိုဩဒိနိတ် ကူးထည့်ပါ။"
    ),
    "nearest_button_label": "📍 ကျွန်ုပ်၏ တည်နေရာ ပို့ပါ",
    "nearest_header_default": "<b>{radius} အတွင်း အနီးဆုံး အိမ်သာများ</b>",
    "nearest_header_widened": ("{widened} အတွင်း မတွေ့ပါ၊ ထို့ကြောင့် {radius} အထိ ချဲ့ထားသည်:"),
    "no_results": (
        "သင့်အနီးတွင် {radius} အတွင်း အိမ်သာ မတွေ့ပါ။\n\n"
        "အနီးတွင် တစ်ခု သိပါက /share ဖြင့် ထည့်ပါ — စက္ကန့်အနည်းငယ် ကြာသည်။"
    ),
    # Search
    "ask_search": "ဘာကို ရှာမလဲ။ အမည် သို့မဟုတ် ဧရိယာ ရိုက်ပါ။",
    "search_header": '"<b>{query}</b>" နှင့် ကိုက်ညီသော ရလဒ်များ',
    "search_no_results": (
        '"<b>{query}</b>" နှင့် ကိုက်ညီသည်မရှိပါ။ စာလုံးပေါင်း ပြောင်းကြည့်ပါ သို့မဟုတ် /share ဖြင့် ထည့်ပါ။'
    ),
    # Share
    "share_button_label": "📍 အိမ်သာ၏ တည်နေရာ ပို့ပါ",
    "share_intro": (
        "➕ <b>အိမ်သာ ထည့်ရန်</b>\n\n"
        "အိမ်သာ၏ တည်နေရာကို ပို့ပါ။ အိမ်သာဘေးတွင် ရပ်ပြီး ပို့ပါက အကောင်းဆုံး "
        "ဖြစ်သည် — မြေပုံပေါ်တွင် အနီးအနား ချထားသော pin လည်း ရပါသည်။\n\n"
        "ထိုနေရာတွင် မရှိပါက 📎 → Location ဖြင့် တည်နေရာ ပူးတွဲပြီး pin ကို "
        "ရွှေ့ပါ၊ သို့မဟုတ် မြေပုံလင့်ခ် / ကိုဩဒိနိတ် (16.7748, 96.1583) ကို "
        "ကူးထည့်ပါ။"
    ),
    "ask_name": "ရပါပြီ။ ဒီနေရာကို ဘယ်လိုခေါ်သလဲ။\n\nအမည် ပို့ပါ၊ ဒါမှမဟုတ် ကျော် ကို နှိပ်ပါ။",
    "share_confirmed": (
        "✅ <b>ထည့်ပြီးပါပြီ — ကျေးဇူးတင်ပါသည်!</b>\n\n"
        "အခြားသူများ ယခု ရှာတွေ့နိုင်ပါပြီ။\n\n"
        '<a href="{link}">ဒီနေရာကို သူငယ်ချင်းထံ ပို့ပါ</a>'
    ),
    "share_duplicate": (
        "ဒါက မြေပုံပေါ်တွင် ရှိပြီးသား နေရာတစ်ခုနှင့် တူနေသည်၊ ခန့်မှန်း {distance} အကွာ:\n\n"
        "<b>{name}</b>\n\nတူညီသော နေရာ ဖြစ်ပါသလား။"
    ),
    "share_duplicate_confirmed": (
        "👍 အတည်ပြုပေးသည့်အတွက် ကျေးဇူးတင်ပါသည် — ဒါက မြေပုံပေါ်တွင် ရှိပြီးသားပါ။"
    ),
    "share_limit_reached": (
        "24 နာရီအတွင်း နေရာ {limit} ခု ထည့်ပြီးပါပြီ၊ ဒါက နေ့စဉ် ကန့်သတ်ချက် "
        "ဖြစ်သည်။ မနက်ဖြန် ထပ်ကြိုးစားပါ။"
    ),
    # My places
    "mine_header": "<b>သင်ထည့်ထားသော နေရာများ</b>",
    "mine_empty": "သင်သည် နေရာ တစ်ခုမှ မထည့်ရသေးပါ။ /share ဖြင့် ထည့်ပါ။",
    "ask_new_name": "ဒီနေရာအတွက် အမည်အသစ် ပို့ပါ။",
    "renamed": "အမည်ပြောင်းပြီးပါပြီ: <b>{name}</b>",
    # Reporting and rating
    "report_thanks": "🚩 အစီရင်ခံပြီးပါပြီ။ ကျေးဇူးတင်ပါသည် — မြေပုံ မှန်ကန်နေအောင် ကူညီပါသည်။",
    "report_already": "ဒါကို အစီရင်ခံပြီးသားပါ။ ဒါပေမယ့် ကျေးဇူးတင်ပါတယ်!",
    "report_hidden": "🚩 အစီရင်ခံပြီး — ဒီနေရာကို ပြန်စစ်ဆေးရန် မြေပုံမှ ဖယ်ထားသည်။",
    "rating_thanks": "ကျေးဇူးတင်ပါသည်! ဒါကို ★{score} ပေးထားသည်။",
    "rating_updated": "ပြင်ပြီးပါပြီ: ★{score}။",
    # Shared status messages
    "not_found": "ဒီနေရာက မြေပုံပေါ်တွင် မရှိတော့ပါ။",
    "not_yours": "ဒါက သင်ထည့်ထားသော နေရာ မဟုတ်ပါ။",
    "delete_confirm": "<b>{name}</b> ကို ဖျက်မလား။ ပြန်ပြင်၍ မရပါ။",
    "deleted": "ဖျက်ပြီးပါပြီ။",
    "nothing_to_skip": "ယခု ကျော်ရန် ဘာမှ မရှိပါ။",
    "draft_expired": "ဒီတောင်းဆိုချက် သက်တမ်းကုန်သွားပါပြီ။ /share ဖြင့် ပြန်စပါ။",
    "send_location_instead": (
        "တည်နေရာကို ပို့ပါ၊ မြေပုံလင့်ခ် သို့မဟုတ် ကိုဩဒိနိတ် "
        "(16.7748, 96.1583) ကို ကူးထည့်ပါ။ Telegram တွင် 📎 → Location ဖြင့် "
        "pin ကို ရွှေ့ပြီး ပို့နိုင်သည်။ ရပ်ရန် /cancel ရိုက်ပါ။"
    ),
    "prompt_dismissed": "✓",
    "cancelled": "ပယ်ဖျက်ပြီးပါပြီ။ ဘာမှ မသိမ်းဆည်းပါ။",
    "error": "ကျွန်ုပ်၏ ဘက်မှာ တစ်ခုခု မှားသွားသည်။ ခဏနေရင် ပြန်ကြိုးစားပါ။",
    "unknown_message": (
        "နားမလည်ပါ။ ခလုတ်တစ်ခု နှိပ်ပါ၊ သို့မဟုတ် /nearest၊ /share၊ /find သို့မဟုတ် /help ကို သုံးပါ။"
    ),
    # Venue card words
    "default_toilet_name": "အများပြည်သူ့ အိမ်သာ",
    "public_toilet": "အများပြည်သူ့ အိမ်သာ",
    "word_free": "အခမဲ့",
    "word_paid": "အခကြေးငွေရှိ",
    "word_accessible": "ဘီးတပ်ကုလားထိုင်ဖြင့် ဝင်နိုင်",
    # Language picker and inline mode
    "choose_language": "ဘာသာစကား ရွေးပါ",
    "language_changed": "ဘာသာစကား: {language}",
    "language_saved": "သိမ်းပြီးပါပြီ။ အောက်ပါ မီနူးကို ယခု {language} ဖြင့် ပြထားသည်။",
    "inline_add_button": "cheebot ဖြင့် တစ်ခု ထည့်ပါ",
}

_EN: dict[str, str] = {
    "menu_nearest": "📍 Nearest",
    "menu_share": "➕ Share",
    "menu_find": "🔍 Find",
    "menu_mine": "📋 My places",
    "menu_about": "ℹ️ About",
    "menu_cancel": "✖️ Cancel",
    "menu_skip": "⏭ Skip",
    "menu_language": "🌐 Language",
    "btn_directions": "🗺 Directions",
    "btn_share": "🔗 Share",
    "btn_report": "🚩 Report",
    "btn_same_place": "✅ Same place",
    "btn_different_place": "🆕 It's different",
    "btn_rename": "✏️ Rename",
    "btn_delete": "🗑 Delete",
    "btn_delete_yes": "✅ Delete",
    "btn_delete_no": "✖️ Keep",
    "welcome": (
        "👋 <b>Welcome to cheebot</b>\n\n"
        "Find a toilet near you, and help other people find theirs. "
        "Free, no account, no ads.\n\n"
        "📍 <b>Nearest</b> — share your location, get the closest toilets\n"
        "➕ <b>Share</b> — add a place you know about\n"
        "🔍 <b>Find</b> — search by name or area"
    ),
    "welcome_inline": (
        "<b>In any chat</b>, type <code>@{username}</code> followed by a place "
        "name to share a toilet there."
    ),
    "welcome_footer": "Tap a button below to start.",
    "help": (
        "<b>How to use cheebot</b>\n\n"
        "/nearest — closest toilets to you\n"
        "/share — add a toilet to the map\n"
        "/find &lt;name or area&gt; — search by text\n"
        "/mine — rename or delete places you added\n"
        "/about — where the data comes from\n"
        "/language — change the language\n"
        "/cancel — stop what you're doing"
    ),
    "help_inline": (
        "<b>In any chat</b>: <code>@{username}</code> + a place name, e.g. "
        "<code>@{username} central station</code>."
    ),
    "about": (
        "<b>About cheebot</b>\n\n"
        "cheebot is free: no ads, no accounts, no tracking.\n\n"
        "<b>Where the data comes from</b>\n"
        "Places are added by people like you, plus public map data from "
        "OpenStreetMap. Map data © OpenStreetMap contributors, available under "
        "the Open Database License (ODbL).\n"
        "https://www.openstreetmap.org/copyright\n\n"
        "<b>Privacy</b>\n"
        "The location you send is used once, to answer that single search, and "
        "is not stored. Submissions keep a salted hash of your account id so we "
        "can stop spam — never your id, name or phone number.\n\n"
        "Something wrong or missing? Tap 🚩 Report on any result, or rate it "
        "1–5 stars.\n\n"
        "Tap 🌐 Language to switch between မြန်မာ, English and 中文."
    ),
    "ask_location_nearest": (
        "Send me your location and I'll list the toilets closest to you. "
        "Searching from somewhere else? Paste a map link or coordinates."
    ),
    "nearest_button_label": "📍 Send my location",
    "nearest_header_default": "<b>Closest toilets within {radius}</b>",
    "nearest_header_widened": (
        "Nothing within {widened}, so I widened the search to {radius}:"
    ),
    "no_results": (
        "I couldn't find any toilets within {radius} of you.\n\n"
        "If you know one nearby, add it with /share — it takes a few seconds."
    ),
    "ask_search": "What should I look for? A name or an area works.",
    "search_header": 'Matches for "<b>{query}</b>"',
    "search_no_results": (
        'Nothing matching "<b>{query}</b>". Try a different spelling, or add it '
        "with /share."
    ),
    "share_button_label": "📍 Send the toilet's location",
    "share_intro": (
        "➕ <b>Add a toilet</b>\n\n"
        "Send me the location of the toilet. Standing next to it gives the best "
        "pin — a map pin you drop nearby works too.\n\n"
        "Not there right now? Attach a location in Telegram (📎 → Location) and "
        "move the pin, or paste a map link or coordinates like "
        "16.7748, 96.1583."
    ),
    "ask_name": "Got it. What's this place called?\n\nSend a name, or tap Skip.",
    "share_confirmed": (
        "✅ <b>Added — thank you!</b>\n\n"
        "Other people can find it now.\n\n"
        '<a href="{link}">Send this place to a friend</a>'
    ),
    "share_duplicate": (
        "This looks like a place that's already on the map, about {distance} "
        "away:\n\n<b>{name}</b>\n\nIs it the same place?"
    ),
    "share_duplicate_confirmed": "👍 Thanks for confirming — it's already on the map.",
    "share_limit_reached": (
        "You've added {limit} places in the last 24 hours, which is the daily "
        "limit. Please try again tomorrow."
    ),
    "mine_header": "<b>Places you added</b>",
    "mine_empty": "You haven't added any places yet. Add one with /share.",
    "ask_new_name": "Send the new name for this place.",
    "renamed": "Renamed to <b>{name}</b>.",
    "report_thanks": "🚩 Reported. Thanks — this helps keep the map honest.",
    "report_already": "You've already reported this one. Thanks though!",
    "report_hidden": (
        "🚩 Reported — this location has been taken off the map pending review."
    ),
    "rating_thanks": "Thanks! You rated this ★{score}.",
    "rating_updated": "Updated: ★{score}.",
    "not_found": "That place is no longer on the map.",
    "not_yours": "That place isn't one you added.",
    "delete_confirm": "Delete <b>{name}</b>? This can't be undone.",
    "deleted": "Deleted.",
    "nothing_to_skip": "There's nothing to skip right now.",
    "draft_expired": "That prompt has expired. Start again with /share.",
    "send_location_instead": (
        "Send me a location, or paste a map link or coordinates like "
        "16.7748, 96.1583. In Telegram you can attach a location "
        "(📎 → Location) and move the pin first. /cancel to stop."
    ),
    "prompt_dismissed": "✓",
    "cancelled": "Cancelled. Nothing was saved.",
    "error": "Something went wrong on my side. Please try again in a moment.",
    "unknown_message": (
        "I didn't get that. Tap a button, or try /nearest, /share, /find or /help."
    ),
    "default_toilet_name": "Public toilet",
    "public_toilet": "Public toilet",
    "word_free": "free",
    "word_paid": "paid",
    "word_accessible": "wheelchair accessible",
    "choose_language": "Choose a language",
    "language_changed": "Language: {language}",
    "language_saved": "Saved. The menu below is now in {language}.",
    "inline_add_button": "Add one with cheebot",
}

_ZH: dict[str, str] = {
    "menu_nearest": "📍 最近",
    "menu_share": "➕ 添加",
    "menu_find": "🔍 搜索",
    "menu_mine": "📋 我的地点",
    "menu_about": "ℹ️ 关于",
    "menu_cancel": "✖️ 取消",
    "menu_skip": "⏭ 跳过",
    "menu_language": "🌐 语言",
    "btn_directions": "🗺 路线",
    "btn_share": "🔗 分享",
    "btn_report": "🚩 举报",
    "btn_same_place": "✅ 就是这里",
    "btn_different_place": "🆕 不是这里",
    "btn_rename": "✏️ 重命名",
    "btn_delete": "🗑 删除",
    "btn_delete_yes": "✅ 删除",
    "btn_delete_no": "✖️ 保留",
    "welcome": (
        "👋 <b>欢迎使用 cheebot</b>\n\n"
        "找到你身边的厕所，也帮别人找到他们需要的。免费、无需注册、没有广告。\n\n"
        "📍 <b>最近</b> — 发送位置，查看最近的厕所\n"
        "➕ <b>添加</b> — 添加你熟悉的地点\n"
        "🔍 <b>搜索</b> — 按名称或区域搜索"
    ),
    "welcome_inline": (
        "<b>在任何聊天中</b>，输入 <code>@{username}</code> 再加上地点名称，"
        "即可分享那里的厕所。"
    ),
    "welcome_footer": "点击下面的按钮开始。",
    "help": (
        "<b>cheebot 使用说明</b>\n\n"
        "/nearest — 离你最近的厕所\n"
        "/share — 把厕所添加到地图\n"
        "/find &lt;名称或区域&gt; — 按文字搜索\n"
        "/mine — 管理你添加的地点\n"
        "/about — 数据来源\n"
        "/language — 切换语言\n"
        "/cancel — 停止当前操作"
    ),
    "help_inline": (
        "<b>在任何聊天中</b>：<code>@{username}</code> + 地点名称，"
        "例如 <code>@{username} 中央车站</code>。"
    ),
    "about": (
        "<b>关于 cheebot</b>\n\n"
        "cheebot 免费：没有广告、无需账号、不做追踪。\n\n"
        "<b>数据从哪来</b>\n"
        "地点由像你一样的人添加，另有来自 OpenStreetMap 的公开地图数据。"
        "Map data © OpenStreetMap contributors，按开放数据库许可 (ODbL) 提供。\n"
        "https://www.openstreetmap.org/copyright\n\n"
        "<b>隐私</b>\n"
        "你发送的位置只用于那一次查询，不会被保存。提交记录中保存的是你账号 id "
        "的加盐哈希，用于防止垃圾信息 —— 从不保存你的 id、姓名或手机号。\n\n"
        "有错误或缺少地点？在任意结果上点 🚩 举报，或给它打 1–5 星。\n\n"
        "点 🌐 语言 可在 မြန်မာ、English、中文 之间切换。"
    ),
    "ask_location_nearest": (
        "发送你的位置，我会列出离你最近的厕所。想从别处搜索？粘贴地图链接或坐标即可。"
    ),
    "nearest_button_label": "📍 发送我的位置",
    "nearest_header_default": "<b>{radius} 内最近的厕所</b>",
    "nearest_header_widened": "{widened} 内没有找到，所以我把范围扩大到 {radius}：",
    "no_results": (
        "在你周围 {radius} 内没有找到厕所。\n\n"
        "如果你知道附近有，用 /share 添加，只需几秒钟。"
    ),
    "ask_search": "想找什么？名称或区域都可以。",
    "search_header": "“<b>{query}</b>” 的搜索结果",
    "search_no_results": (
        "没有找到与“<b>{query}</b>”匹配的内容。换个写法试试，或用 /share 添加。"
    ),
    "share_button_label": "📍 发送厕所的位置",
    "share_intro": (
        "➕ <b>添加厕所</b>\n\n"
        "发送这个厕所的位置。站在旁边发送最准确，在地图上附近放一个图钉也可以。\n\n"
        "不在旁边？在 Telegram 中通过 📎 → 位置 移动图钉后发送，"
        "或粘贴地图链接、坐标（如 16.7748, 96.1583）。"
    ),
    "ask_name": "收到。这个地方叫什么？\n\n发送名称，或点“跳过”。",
    "share_confirmed": (
        "✅ <b>已添加 —— 谢谢！</b>\n\n"
        "其他人现在可以找到它了。\n\n"
        '<a href="{link}">把这个地点分享给朋友</a>'
    ),
    "share_duplicate": (
        "这看起来和地图上已有一个地点很近，大约相距 {distance}：\n\n"
        "<b>{name}</b>\n\n是同一个地方吗？"
    ),
    "share_duplicate_confirmed": "👍 谢谢确认 —— 它已经在地图上了。",
    "share_limit_reached": (
        "你在过去 24 小时内已添加 {limit} 个地点，达到每日上限。请明天再试。"
    ),
    "mine_header": "<b>你添加的地点</b>",
    "mine_empty": "你还没有添加任何地点。用 /share 添加一个。",
    "ask_new_name": "发送这个地方的新名称。",
    "renamed": "已重命名为 <b>{name}</b>",
    "report_thanks": "🚩 已举报。谢谢 —— 这让地图更可靠。",
    "report_already": "你已经举报过这个了。不过还是谢谢！",
    "report_hidden": "🚩 已举报 —— 这个地点已被暂时从地图上移除，等待复核。",
    "rating_thanks": "谢谢！你给它打了 ★{score}。",
    "rating_updated": "已更新：★{score}。",
    "not_found": "这个地点已不在地图上。",
    "not_yours": "这个地点不是你添加的。",
    "delete_confirm": "要删除 <b>{name}</b> 吗？此操作无法撤销。",
    "deleted": "已删除。",
    "nothing_to_skip": "目前没有可跳过的内容。",
    "draft_expired": "该提示已过期。请用 /share 重新开始。",
    "send_location_instead": (
        "请发送位置，或粘贴地图链接、坐标（如 16.7748, 96.1583）。"
        "在 Telegram 中可通过 📎 → 位置 移动图钉后发送。输入 /cancel 可停止。"
    ),
    "prompt_dismissed": "✓",
    "cancelled": "已取消，没有保存任何内容。",
    "error": "我这边出了点问题，请稍后再试。",
    "unknown_message": (
        "我没看懂。点一下按钮，或试试 /nearest、/share、/find、/help。"
    ),
    "default_toilet_name": "公共厕所",
    "public_toilet": "公共厕所",
    "word_free": "免费",
    "word_paid": "收费",
    "word_accessible": "无障碍",
    "choose_language": "选择语言",
    "language_changed": "语言：{language}",
    "language_saved": "已保存。下面的菜单现在是{language}。",
    "inline_add_button": "用 cheebot 添加一个",
}

MESSAGES: dict[str, dict[str, str]] = {
    "my": _MY,
    "en": _EN,
    "zh": _ZH,
}
