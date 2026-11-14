import ctypes
import ctypes.util
from pathlib import Path
import re
import unittest


MAIN = (Path(__file__).resolve().parents[1] / "UnifiedNativeBags335" / "UnifiedNativeBags335.lua").read_text()


def lua_function(name, next_marker):
    start = MAIN.index(name)
    end = MAIN.index(next_marker, start)
    return MAIN[start:end]


def run_lua(source):
    library = ctypes.util.find_library("lua5.4") or ctypes.util.find_library("lua")
    if not library:
        raise unittest.SkipTest("system Lua library is unavailable")
    lua = ctypes.CDLL(library)
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lua.luaL_loadstring.restype = ctypes.c_int
    lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
    lua.lua_pcallk.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]

    state = lua.luaL_newstate()
    try:
        lua.luaL_openlibs(state)
        result = lua.luaL_loadstring(state, source.encode())
        if result == 0:
            result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
        if result != 0:
            error = lua.lua_tolstring(state, -1, None)
            raise AssertionError(error.decode() if error else f"Lua error {result}")
    finally:
        lua.lua_close(state)


class ScrollFrameRegressionTests(unittest.TestCase):
    def test_scroll_frame_creation_uses_named_wrath_template(self):
        helper = lua_function(
            'local function CreateNamedScrollFrame',
            'local function ScanContainers',
        )
        run_lua(
            r'''
local created
function CreateFrame(kind, name, parent, template)
    assert(kind == "ScrollFrame")
    assert(name, "Wrath UIPanelScrollFrameTemplate requires a name")
    assert(template == "UIPanelScrollFrameTemplate")
    created = { name = name, parent = parent }
    function created:GetName() return self.name end
    return created
end
'''
            + helper
            + r'''
local scroll = CreateNamedScrollFrame({}, "TestScrollFrame")
assert(scroll:GetName() == "TestScrollFrame")
'''
        )

    def test_all_template_scroll_frames_have_unique_names_and_children(self):
        self.assertIn('frameName .. "ScrollFrame"', MAIN)
        self.assertIn('"UnifiedNativeBags335GuildBankScrollFrame"', MAIN)
        self.assertNotRegex(
            MAIN,
            r'CreateFrame\("ScrollFrame",\s*nil,.*"UIPanelScrollFrameTemplate"',
        )
        self.assertEqual(MAIN.count('scroll:SetScrollChild(child)'), 2)

    def test_wrath_scroll_range_lookup_can_resolve_template_globals(self):
        names = (
            "UnifiedNativeBags335BagsFrameScrollFrame",
            "UnifiedNativeBags335BankFrameScrollFrame",
            "UnifiedNativeBags335GuildBankScrollFrame",
        )
        for name in names:
            globals_by_name = {
                name + "ScrollBar": object(),
                name + "ScrollBarScrollUpButton": object(),
                name + "ScrollBarScrollDownButton": object(),
                name + "ScrollBarThumbTexture": object(),
            }
            self.assertIsNotNone(globals_by_name[name + "ScrollBar"])
            self.assertIsNotNone(globals_by_name[name + "ScrollBarScrollUpButton"])
            self.assertIsNotNone(globals_by_name[name + "ScrollBarScrollDownButton"])


class ReagentItemCacheRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reagent_code = lua_function(
            'function UB:BuildReagentItems',
            'function UB:ReagentStatusText',
        )

    def run_reagent_harness(self, assertions):
        prefix = r'''
ITEM_INFO_RETRY_INTERVAL = 0.5
ITEM_INFO_MAX_RETRIES = 20
UB = {
    pendingItemInfo = {}, exhaustedItemInfo = {}, itemInfoRetryElapsed = 0,
    reagentAPI = {}, refreshes = 0,
}
local snapshot = { [101] = 7, [202] = 43, [303] = 2 }
function UB.reagentAPI:GetVirtualItems() return snapshot end
local info = {
    [101] = { "Arcane Dust", "item:101", 2, 1, 1, "Trade Goods", "Enchanting", 20, "", "Icon101" },
    [303] = { "Copper Bar", "item:303", 1, 1, 1, "Trade Goods", "Metal", 20, "", "Icon303" },
}
local icons = { [101] = "Icon101", [303] = "Icon303" }
local queries = {}
function GetItemInfo(id)
    queries[id] = (queries[id] or 0) + 1
    local value = info[id]
    if value then return table.unpack(value) end
end
function GetItemIcon(id) return icons[id] end
function MatchesSearch() return true end
function UB:QueueRefresh() self.refreshes = self.refreshes + 1 end
UB.bankDisplay = { view = "reagents", frame = { IsShown = function() return true end } }
'''
        run_lua(prefix + self.reagent_code + assertions)

    def test_reagent_refresh_preserves_multiple_ids_quantities_and_tooltip_links(self):
        self.run_reagent_harness(
            r'''
local items = UB:BuildReagentItems("")
assert(#items == 3)
local byID = {}
for _, item in ipairs(items) do byID[item.itemID] = item end
assert(byID[101].count == 7 and byID[101].link == "item:101")
assert(byID[202].count == 43 and byID[202].itemID == 202)
assert(byID[202].link == nil and byID[202].texture == nil)
assert(byID[303].count == 2 and byID[303].link == "item:303")
assert(UB.pendingItemInfo[202] == 0)
'''
        )

    def test_delayed_icon_resolution_refreshes_without_inventory_transfer(self):
        self.run_reagent_harness(
            r'''
UB:BuildReagentItems("")
UB:RetryMissingItemInfo(0.25)
assert(UB.refreshes == 0 and UB.pendingItemInfo[202] == 0)
info[202] = { "Dream Shard", "item:202", 3, 1, 1, "Trade Goods", "Enchanting", 20, "", "Icon202" }
icons[202] = "Icon202"
UB:RetryMissingItemInfo(0.25)
assert(UB.pendingItemInfo[202] == nil and UB.refreshes == 1)
local items = UB:BuildReagentItems("")
local found
for _, item in ipairs(items) do if item.itemID == 202 then found = item end end
assert(found and found.count == 43 and found.texture == "Icon202" and found.link == "item:202")
'''
        )

    def test_item_icon_fallback_handles_partial_cache_information(self):
        self.run_reagent_harness(
            r'''
icons[202] = "Icon202"
local items = UB:BuildReagentItems("")
local found
for _, item in ipairs(items) do if item.itemID == 202 then found = item end end
assert(found and found.texture == "Icon202" and found.count == 43)
assert(UB.pendingItemInfo[202] == 0, "name/link resolution should still be retried")
'''
        )

    def test_missing_cache_polling_is_bounded(self):
        self.run_reagent_harness(
            r'''
UB:BuildReagentItems("")
for i = 1, 20 do UB:RetryMissingItemInfo(0.5) end
assert(UB.pendingItemInfo[202] == nil)
assert(UB.exhaustedItemInfo[202] == true)
local count = queries[202]
UB:RetryMissingItemInfo(10)
assert(queries[202] == count)
'''
        )

    def test_switching_views_and_closed_bank_pause_then_reopen_resets_retries(self):
        self.run_reagent_harness(
            r'''
UB:BuildReagentItems("")
local count = queries[202]
UB.bankDisplay.view = "bank"
UB:RetryMissingItemInfo(1)
assert(queries[202] == count)
UB.bankDisplay.view = "reagents"
UB.bankDisplay.frame.IsShown = function() return false end
UB:RetryMissingItemInfo(1)
assert(queries[202] == count)
UB.exhaustedItemInfo[202] = true
UB:ResetMissingItemRetries()
assert(next(UB.pendingItemInfo) == nil and next(UB.exhaustedItemInfo) == nil)
UB.bankDisplay.frame.IsShown = function() return true end
UB:BuildReagentItems("")
assert(UB.pendingItemInfo[202] == 0)
'''
        )


if __name__ == "__main__":
    unittest.main()
