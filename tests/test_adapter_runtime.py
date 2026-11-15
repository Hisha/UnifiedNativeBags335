import ctypes
import ctypes.util
from pathlib import Path
import unittest


ADAPTER = (Path(__file__).resolve().parents[1] / "UnifiedNativeBags335" / "NativeReagentsAdapter.lua").read_text()


HARNESS = r'''
local calls = { deposits = {}, withdrawals = {}, auto = {} }
local callback
local presentation
local bankView = "bank"
local items = { [123] = 75 }

NativeReagents = {
    RegisterPresentation = function(value) presentation = value; return true end,
    GetPresentation = function() return presentation end,
    RegisterCallback = function(value) callback = value; return true end,
    UnregisterCallback = function() callback = nil end,
    IsAvailable = function() return true end,
    IsReady = function() return true end,
    IsBankOpen = function() return true end,
    SetBankView = function(value)
        if value ~= "bank" and value ~= "reagents" then return false end
        bankView = value
        return true
    end,
    GetStatus = function() return "ready" end,
    GetLastError = function() return nil end,
    GetItems = function() return items end,
    GetQuantity = function(id) return items[id] or 0 end,
    GetAutoDeposit = function() return false end,
    RequestSync = function() return true end,
    DepositAll = function() calls.depositAll = (calls.depositAll or 0) + 1; return true end,
    Deposit = function(id, quantity)
        table.insert(calls.deposits, { id, quantity })
        return true, #calls.deposits
    end,
    Withdraw = function(id, quantity)
        table.insert(calls.withdrawals, { id, quantity })
        return true
    end,
    SetAutoDeposit = function(enabled) table.insert(calls.auto, enabled); return true end,
}

local owner = {
    CacheReagents = function() end,
    QueueRefresh = function() end,
    UpdateAutoDepositControl = function() end,
    UpdateReagentControls = function() end,
}

local adapter = UnifiedNativeBags335NativeReagents
assert(adapter:Attach(owner))
assert(presentation and presentation.addon == "UnifiedNativeBags335")
assert(adapter:GetVirtualItems()[123] == 75)
assert(adapter:SetBankView("reagents") and bankView == "reagents")
assert(adapter:SetBankView("bank") and bankView == "bank")

assert(adapter:Deposit(123, 40))
assert(calls.deposits[1][1] == 123 and calls.deposits[1][2] == 40)
assert(not adapter:Deposit(123, 40), "duplicate deposit must be rejected before sync")
callback("ITEMS_UPDATED", items)
assert(adapter:Deposit(123, 40), "authoritative sync must release pending request")

assert(adapter:TrackCursorItem(123, 17, 0, 1))
CursorHasItem = function() return true end
GetCursorInfo = function() return "item", 123, "item:123" end
assert(adapter:DepositTrackedCursor())
assert(calls.deposits[#calls.deposits][2] == 17)
assert(adapter.cursorSelection.quantity == 17, "submission must not clear tracked cursor")

callback("ITEMS_UPDATED", items)
assert(adapter:RequestWithdraw(123, 20))
assert(not adapter:RequestWithdraw(123, 20), "duplicate withdrawal must be rejected")
callback("ERROR", "bag-full", "WITHDRAW", 1)
assert(adapter:RequestWithdraw(123, 20), "error must release withdrawal pending state")

assert(adapter:SetAutoDepositEnabled(true))
assert(not adapter:SetAutoDepositEnabled(true), "setting changes must be debounced")
callback("AUTO_DEPOSIT_CHANGED", true)
assert(adapter:SetAutoDepositEnabled(false))

assert(adapter:DepositAll())
assert(not adapter:DepositAll(), "Deposit All must be debounced")
callback("ITEMS_UPDATED", items)
assert(adapter:DepositAll())
'''


class AdapterRuntimeTests(unittest.TestCase):
    def test_adapter_state_machine(self):
        library = ctypes.util.find_library("lua5.4") or ctypes.util.find_library("lua")
        if not library:
            self.skipTest("system Lua library is unavailable")
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
        self.assertTrue(state)
        try:
            lua.luaL_openlibs(state)
            source = (ADAPTER + "\n" + HARNESS).encode()
            result = lua.luaL_loadstring(state, source)
            if result == 0:
                result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
            if result != 0:
                error = lua.lua_tolstring(state, -1, None)
                self.fail(error.decode() if error else f"Lua error {result}")
        finally:
            lua.lua_close(state)


if __name__ == "__main__":
    unittest.main()
