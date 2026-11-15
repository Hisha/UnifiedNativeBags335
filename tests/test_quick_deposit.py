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


class InheritedContainerClickRuntimeTests(unittest.TestCase):
    """Exercise the real physical-inventory path used in the live client."""

    @classmethod
    def setUpClass(cls):
        cls.set_bank_view = lua_function(
            "function UB:SetBankView(view)",
            "function UB:ShowBags",
        )

    def run_click_model(self, actions, assertions, deposit_result="true"):
        run_lua(
            r'''
local nativeView = "bank"
local nativeBankOpen = true
local quickCalls, useCalls, modifiedCalls, secureCalls = 0, 0, 0, 0
local depositResult = DEPOSIT_RESULT

NativeReagents = {}
function NativeReagents.SetBankView(view)
    if view ~= "bank" and view ~= "reagents" then return false end
    nativeView = view
    return true
end
function NativeReagents.IsReagentBankViewActive()
    return nativeBankOpen and nativeView == "reagents"
end
function NativeReagents.DepositInventoryItem(bag, slot)
    quickCalls = quickCalls + 1
    assert(bag == 2 and slot == 7)
    return depositResult
end

function UseContainerItem(bag, slot)
    useCalls = useCalls + 1
    assert(bag == 2 and slot == 7)
end

-- Native Reagents retains Blizzard's inherited container handler and wraps it.
local function StockContainerFrameItemButton_OnClick(button, mouseButton)
    if mouseButton == "RightButton" then UseContainerItem(button:GetParent():GetID(), button:GetID()) end
end
local function ContainerFrameItemButton_OnClick(button, mouseButton)
    local parent = button:GetParent()
    if mouseButton == "RightButton" and NativeReagents.IsReagentBankViewActive() and
        NativeReagents.DepositInventoryItem(parent:GetID(), button:GetID()) then
        return
    end
    return StockContainerFrameItemButton_OnClick(button, mouseButton)
end

local parent = { GetID = function() return 2 end }
local button = {
    GetParent = function() return parent end,
    GetID = function() return 7 end,
}
local function DispatchClick(mouseButton, modified)
    -- ContainerFrameItemButtonTemplate routes modifiers to a different script.
    if modified then modifiedCalls = modifiedCalls + 1
    else ContainerFrameItemButton_OnClick(button, mouseButton) end
    -- No SecureActionButton attributes exist on this template/button, so
    -- there is no independent post-OnClick item action to execute.
    local secureType = nil
    if secureType then secureCalls = secureCalls + 1 end
end

local adapter = {
    SetBankView = function(_, view) return NativeReagents.SetBankView(view) end,
}
UB = {
    bankOpen = true,
    reagentAPI = adapter,
    bankDisplay = {
        view = "bank",
        scroll = { SetVerticalScroll = function() end },
    },
    ApplyDisplayGeometry = function() end,
    RefreshDisplay = function() end,
}
'''.replace("DEPOSIT_RESULT", deposit_result)
            + self.set_bank_view
            + actions
            + assertions
        )

    def test_mismatched_addon_and_native_views_reproduce_ordinary_bank_transfer(self):
        self.run_click_model(
            '\nUB.bankDisplay.view = "reagents"\nDispatchClick("RightButton", false)\n',
            "assert(nativeView == 'bank' and quickCalls == 0 and useCalls == 1)",
        )

    def test_view_sync_allows_reagent_deposit_without_ordinary_transfer(self):
        self.run_click_model(
            '\nUB:SetBankView("reagents")\nDispatchClick("RightButton", false)\n',
            "assert(nativeView == 'reagents' and quickCalls == 1 and useCalls == 0 and secureCalls == 0)",
        )

    def test_deposit_rejection_falls_through_inherited_handler_once(self):
        self.run_click_model(
            '\nUB:SetBankView("reagents")\nDispatchClick("RightButton", false)\n',
            "assert(quickCalls == 1 and useCalls == 1 and secureCalls == 0)",
            deposit_result="false",
        )

    def test_non_reagent_server_response_preserves_ordinary_bank_fallback(self):
        self.run_click_model(
            r'''
UB:SetBankView("reagents")
DispatchClick("RightButton", false)
-- Native Reagents owns this asynchronous NOT_REAGENT fallback after it
-- revalidates the source slot; model the accepted public API contract here.
UseContainerItem(2, 7)
''',
            "assert(quickCalls == 1 and useCalls == 1 and secureCalls == 0)",
        )

    def test_switching_back_to_bank_restores_ordinary_banking(self):
        self.run_click_model(
            '\nUB:SetBankView("reagents")\nUB:SetBankView("bank")\nDispatchClick("RightButton", false)\n',
            "assert(nativeView == 'bank' and quickCalls == 0 and useCalls == 1)",
        )

    def test_modifier_click_bypasses_quick_deposit_and_ordinary_use(self):
        self.run_click_model(
            '\nUB:SetBankView("reagents")\nDispatchClick("RightButton", true)\n',
            "assert(modifiedCalls == 1 and quickCalls == 0 and useCalls == 0 and secureCalls == 0)",
        )

    def test_bank_closed_uses_normal_inherited_inventory_behavior(self):
        self.run_click_model(
            '\nUB:SetBankView("reagents")\nnativeBankOpen = false\nDispatchClick("RightButton", false)\n',
            "assert(quickCalls == 0 and useCalls == 1 and secureCalls == 0)",
        )

    def test_inventory_buttons_use_inherited_container_handler_without_secure_attributes(self):
        button_factory = lua_function(
            "function UB:GetContainerButton",
            "local function SetCheckText",
        )
        self.assertIn('"ContainerFrameItemButtonTemplate"', button_factory)
        self.assertNotIn("SecureActionButtonTemplate", button_factory)
        self.assertNotIn("SetAttribute", button_factory)
        self.assertNotIn('SetScript("OnClick"', button_factory)

    def test_layout_assigns_inventory_bag_and_slot_to_blizzard_ids(self):
        layout = lua_function("function UB:LayoutItems", "function UB:RefreshDisplay")
        self.assertIn("b.bag = data.bag", layout)
        self.assertIn("b.slot = data.slot", layout)
        self.assertIn("parent:SetID(data.bag)", layout)
        self.assertIn("b:SetID(data.slot)", layout)


if __name__ == "__main__":
    unittest.main()
