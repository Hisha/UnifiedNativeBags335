import ctypes
import ctypes.util
from pathlib import Path
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


class QuickDepositRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = lua_function(
            "local function HandleInventoryItemRightClick",
            "function UB:GetCustomButton",
        )

    def run_handler(self, setup, assertions):
        run_lua(
            r'''
local nativeCalls, useCalls = 0, 0
UB = { bankOpen = false, guildBankOpen = false, bankDisplay = { view = "bank" } }
MerchantFrame = { IsShown = function() return false end }
function UseContainerItem(bag, slot)
    useCalls = useCalls + 1
    assert(bag == 2 and slot == 7)
end
local button = { bag = 2, slot = 7 }
'''
            + setup
            + self.handler
            + "\nHandleInventoryItemRightClick(button)\n"
            + assertions
        )

    def test_reagent_right_click_is_delegated_without_duplicate_use(self):
        self.run_handler(
            r'''
UB.bankOpen = true
UB.bankDisplay.view = "reagents"
NativeReagents = { DepositInventoryItem = function(bag, slot)
    nativeCalls = nativeCalls + 1
    assert(bag == 2 and slot == 7)
    return true
end }
''',
            "assert(nativeCalls == 1 and useCalls == 0)",
        )

    def test_non_reagent_transfer_remains_owned_by_native_reagents(self):
        self.run_handler(
            r'''
UB.bankOpen = true
UB.bankDisplay.view = "reagents"
NativeReagents = { DepositInventoryItem = function()
    nativeCalls = nativeCalls + 1
    -- A handled QUICK_DEPOSIT later falls back itself after NOT_REAGENT.
    return true
end }
''',
            "assert(nativeCalls == 1 and useCalls == 0)",
        )

    def test_ordinary_bank_view_uses_normal_bank_transfer(self):
        self.run_handler(
            r'''
UB.bankOpen = true
NativeReagents = { DepositInventoryItem = function()
    nativeCalls = nativeCalls + 1
    return true
end }
''',
            "assert(nativeCalls == 0 and useCalls == 1)",
        )

    def test_bank_closed_preserves_secure_inventory_behavior(self):
        self.run_handler(
            r'''
NativeReagents = { DepositInventoryItem = function()
    nativeCalls = nativeCalls + 1
    return true
end }
''',
            "assert(nativeCalls == 0 and useCalls == 0)",
        )

    def test_unavailable_api_falls_back_to_existing_bank_behavior(self):
        self.run_handler(
            'UB.bankOpen = true\nUB.bankDisplay.view = "reagents"\nNativeReagents = nil\n',
            "assert(nativeCalls == 0 and useCalls == 1)",
        )

    def test_unhandled_api_result_falls_back_once(self):
        self.run_handler(
            r'''
UB.bankOpen = true
UB.bankDisplay.view = "reagents"
NativeReagents = { DepositInventoryItem = function()
    nativeCalls = nativeCalls + 1
    return false
end }
''',
            "assert(nativeCalls == 1 and useCalls == 1)",
        )

    def test_modifier_paths_still_precede_ordinary_right_click(self):
        click = lua_function('b:SetScript("OnClick"', 'b:SetScript("OnDragStart"')
        delegate = click.index("HandleInventoryItemRightClick(button)")
        self.assertLess(click.index("HandleModifiedItemClick(button.link)"), delegate)
        self.assertLess(click.index('IsModifiedClick("SPLITSTACK")'), delegate)
        self.assertIn("OpenStackSplitFrame(button.count, button", click)


if __name__ == "__main__":
    unittest.main()
