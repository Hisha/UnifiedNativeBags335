from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "UnifiedNativeBags335"
MAIN = (ADDON / "UnifiedNativeBags335.lua").read_text()
ADAPTER = (ADDON / "NativeReagentsAdapter.lua").read_text()
TOC = (ADDON / "UnifiedNativeBags335.toc").read_text()


class IntegrationContractTests(unittest.TestCase):
    def test_manifest_targets_wrath_and_reuses_saved_variables(self):
        self.assertIn("## Interface: 30300", TOC)
        self.assertIn("## SavedVariables: UnifiedBags335DB", TOC)
        self.assertLess(TOC.index("NativeReagentsAdapter.lua"), TOC.index("UnifiedNativeBags335.lua"))

    def test_adapter_uses_public_api_without_raw_protocol(self):
        for method in (
            "GetItems", "GetQuantity", "Deposit", "DepositAll", "Withdraw",
            "GetAutoDeposit", "SetAutoDeposit", "RegisterCallback",
            "RegisterPresentation", "IsBankOpen", "SetBankView", "GetStatus",
        ):
            self.assertRegex(ADAPTER, rf"\b{method}\b")
        self.assertNotIn("SendAddonMessage", ADAPTER)
        self.assertNotRegex(ADAPTER, r'["\']NRB["\']')

    def test_authoritative_updates_and_request_debouncing(self):
        self.assertIn('event == "ITEMS_UPDATED"', ADAPTER)
        self.assertIn('event == "ERROR"', ADAPTER)
        self.assertIn("self.pendingDeposits[key]", ADAPTER)
        self.assertIn("self.withdrawPending", ADAPTER)
        self.assertNotRegex(ADAPTER, r"GetVirtualItems\(\).*[-+]", "adapter must not mutate snapshots")

    def test_cursor_quantity_is_tracked_and_not_cleared_on_submit(self):
        self.assertIn("TrackCursorItem", ADAPTER)
        self.assertIn("selection.quantity", ADAPTER)
        deposit_body = ADAPTER.split("function Adapter:DepositTrackedCursor()", 1)[1].split("\nend", 1)[0]
        self.assertNotIn("ClearCursor", deposit_body)
        self.assertNotIn("DeleteCursor", deposit_body)
        self.assertIn("SplitContainerItem", MAIN)

    def test_bank_reagent_controls_share_existing_window(self):
        self.assertIn('MakeTab("Bank", "bank"', MAIN)
        self.assertIn('MakeTab("Reagent Storage", "reagents"', MAIN)
        self.assertIn('deposit:SetText("Deposit Reagents")', MAIN)
        self.assertIn('autoText:SetText("Auto Deposit")', MAIN)
        self.assertNotIn("CreateReagentDisplay", MAIN)

    def test_inventory_bank_and_guild_regression_surfaces_remain(self):
        required_functions = (
            "BuildContainerItems", "CreateDisplay", "LayoutItems", "ToggleBags",
            "ShowBank", "CreateGuildDisplay", "ShowGuildBank", "OpenGuildTabEdit",
            "CreateBagSlotStrip", "AddAccountCounts",
        )
        for name in required_functions:
            self.assertIn(f"function UB:{name}", MAIN)
        for api in (
            "PickupContainerItem", "SplitContainerItem", "UseContainerItem",
            "PickupGuildBankItem", "SplitGuildBankItem", "AutoStoreGuildBankItem",
        ):
            self.assertIn(api, MAIN)

    def test_coexistence_is_fail_closed(self):
        self.assertIn("IsAddOnLoaded(\"UnifiedBags335\")", MAIN)
        self.assertIn("self:UnregisterAllEvents()", MAIN)


if __name__ == "__main__":
    unittest.main()
