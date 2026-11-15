-- Public Native Reagents API adapter for UnifiedNativeBags335.
-- Storage remains authoritative in NativeReagents; this file owns only UI
-- request state and cursor quantities that the 3.3.5 cursor cannot report.
local Adapter = {}
_G.UnifiedNativeBags335NativeReagents = Adapter

Adapter.owner = nil
Adapter.api = nil
Adapter.presentation = nil
Adapter.callbackOwner = {}
Adapter.pendingDeposits = {}
Adapter.withdrawPending = false
Adapter.depositAllPending = false
Adapter.autoPending = false
Adapter.cursorSelection = nil

local function Notice(message)
    if DEFAULT_CHAT_FRAME then
        DEFAULT_CHAT_FRAME:AddMessage("|cff4fc3f7UnifiedNativeBags335:|r " .. tostring(message))
    end
end

local function IsInteger(value)
    return value and value > 0 and value == math.floor(value)
end

function Adapter:Attach(owner)
    local api = _G.NativeReagents
    if self.api == api and self.owner == owner then return true end
    if not api or type(api.RegisterCallback) ~= "function" or
        type(api.RegisterPresentation) ~= "function" then
        return false
    end

    self.owner, self.api = owner, api
    self.presentation = self.presentation or { addon = "UnifiedNativeBags335" }
    if not api.RegisterPresentation(self.presentation) then
        Notice("another addon already owns the Native Reagents presentation.")
        self.api = nil
        return false
    end

    api.RegisterCallback(function(event, ...)
        Adapter:OnNativeEvent(event, ...)
    end, self.callbackOwner)
    return true
end

function Adapter:Detach()
    if self.api and self.api.UnregisterCallback then
        self.api.UnregisterCallback(self.callbackOwner)
    end
    if self.api and self.api.GetPresentation and
        self.api.GetPresentation() == self.presentation then
        self.api.RegisterPresentation(nil)
    end
    self.api, self.owner = nil, nil
end

function Adapter:IsAvailable()
    return self.api and self.api.IsAvailable and self.api.IsAvailable() or false
end

function Adapter:IsReady()
    return self.api and self.api.IsReady and self.api.IsReady() or false
end

function Adapter:IsBankOpen()
    return self.api and self.api.IsBankOpen and self.api.IsBankOpen() or false
end

function Adapter:SetBankView(view)
    if not self.api or type(self.api.SetBankView) ~= "function" then return false end
    return self.api.SetBankView(view) and true or false
end

function Adapter:GetStatus()
    return self.api and self.api.GetStatus and self.api.GetStatus() or "unavailable"
end

function Adapter:GetLastError()
    return self.api and self.api.GetLastError and self.api.GetLastError() or nil
end

function Adapter:GetVirtualItems()
    if not self:IsReady() or not self.api.GetItems then return {} end
    return self.api.GetItems() or {}
end

function Adapter:GetStored(itemID)
    if not self:IsReady() or not self.api.GetQuantity then return 0 end
    return tonumber(self.api.GetQuantity(itemID)) or 0
end

function Adapter:IsServerAvailable()
    return self:IsAvailable()
end

function Adapter:GetAutoDepositEnabled()
    return self.api and self.api.GetAutoDeposit and self.api.GetAutoDeposit() or false
end

function Adapter:SetAutoDepositEnabled(enabled)
    if self.autoPending or not self:IsBankOpen() or not self.api or
        type(self.api.SetAutoDeposit) ~= "function" then return false end
    local accepted = self.api.SetAutoDeposit(enabled and true or false)
    if accepted then self.autoPending = true end
    return accepted and true or false
end

function Adapter:RequestSync()
    if self.api and self.api.RequestSync then return self.api.RequestSync() end
    return false
end

function Adapter:RequestAutoDepositState()
    -- BANKOPEN makes the server return the authoritative setting.  There is no
    -- separate public query, so a normal sync is the only safe refresh here.
    return self:RequestSync()
end

function Adapter:DepositAll()
    if self.depositAllPending or not self:IsReady() or not self:IsBankOpen() or
        not self.api or type(self.api.DepositAll) ~= "function" then return false end
    local accepted = self.api.DepositAll()
    if accepted then self.depositAllPending = true end
    return accepted and true or false
end

function Adapter:Deposit(itemID, quantity)
    itemID, quantity = tonumber(itemID), tonumber(quantity)
    if not IsInteger(itemID) or not IsInteger(quantity) or not self:IsReady() or
        not self:IsBankOpen() or not self.api or type(self.api.Deposit) ~= "function" then
        return false
    end
    local key = tostring(itemID) .. ":" .. tostring(quantity)
    if self.pendingDeposits[key] then return false end
    local accepted, request = self.api.Deposit(itemID, quantity)
    if accepted then
        self.pendingDeposits[key] = request or true
        return true
    end
    return false
end

function Adapter:RequestWithdraw(itemID, quantity)
    itemID, quantity = tonumber(itemID), tonumber(quantity)
    if self.withdrawPending or not IsInteger(itemID) or not IsInteger(quantity) or
        quantity > self:GetStored(itemID) or not self:IsBankOpen() or not self.api or
        type(self.api.Withdraw) ~= "function" then return false end
    local accepted = self.api.Withdraw(itemID, quantity)
    if accepted then self.withdrawPending = true end
    return accepted and true or false
end

function Adapter:TrackCursorItem(itemID, quantity, bag, slot)
    itemID, quantity = tonumber(itemID), tonumber(quantity)
    if not IsInteger(itemID) or not IsInteger(quantity) then
        self.cursorSelection = nil
        return false
    end
    self.cursorSelection = {
        itemID = itemID,
        quantity = quantity,
        bag = bag,
        slot = slot,
        trackedAt = GetTime and GetTime() or 0,
    }
    return true
end

function Adapter:ClearCursorSelection()
    self.cursorSelection = nil
end

function Adapter:DepositTrackedCursor()
    local selection = self.cursorSelection
    if not selection or not CursorHasItem or not CursorHasItem() then return false end

    -- GetCursorInfo does not expose a dependable selected quantity on 3.3.5a,
    -- but its item ID is useful for rejecting a stale tracked split.
    if GetCursorInfo then
        local cursorType, cursorItemID = GetCursorInfo()
        if cursorType ~= "item" or (tonumber(cursorItemID) and
            tonumber(cursorItemID) ~= selection.itemID) then
            return false
        end
    end

    local accepted = self:Deposit(selection.itemID, selection.quantity)
    -- Deliberately retain both the cursor and its tracked quantity.  The server
    -- owns inventory mutation; the next cursor pickup or clear replaces it.
    return accepted
end

function Adapter:ClearPending()
    self.pendingDeposits = {}
    self.withdrawPending = false
    self.depositAllPending = false
end

function Adapter:OnNativeEvent(event, ...)
    if event == "ITEMS_UPDATED" then
        self:ClearPending()
    elseif event == "AUTO_DEPOSIT_CHANGED" then
        self.autoPending = false
    elseif event == "ERROR" then
        self:ClearPending()
        self.autoPending = false
    elseif event == "BANK_CLOSED" then
        self:ClearPending()
        self.autoPending = false
        self:ClearCursorSelection()
    end

    local owner = self.owner
    if not owner then return end
    if event == "ITEMS_UPDATED" then
        owner:CacheReagents()
    end
    if event == "ITEMS_UPDATED" or event == "STATUS_CHANGED" or
        event == "SYNC_FAILED" or event == "AVAILABLE" or event == "ERROR" or
        event == "BANK_OPENED" or event == "BANK_CLOSED" then
        owner:QueueRefresh()
    end
    if event == "AUTO_DEPOSIT_CHANGED" or event == "ERROR" or
        event == "BANK_OPENED" or event == "BANK_CLOSED" then
        owner:UpdateAutoDepositControl()
        owner:UpdateReagentControls()
    end
end
