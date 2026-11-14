# UnifiedNativeBags335

UnifiedNativeBags335 is a conventional World of Warcraft **3.3.5a** addon that provides one unified interface for Bags, Bank, Reagent Storage, and Guild Bank. It is the direct successor to UnifiedBags335 and preserves that addon's windows, layout, search, movement, stack splitting, tooltips, quality display, saved positioning, and guild-bank behavior.

Reagent Storage is backed exclusively by the public client API supplied by [`mod-native-reagents`](https://github.com/Hisha/mod-native-reagents). The addon does not send `NRB` messages, maintain a second storage ledger, replace protected FrameXML, or implement any server storage logic.

## Requirements

- World of Warcraft 3.3.5a (build 12340).
- A server/client installation of `mod-native-reagents` whose protected client files expose `NativeReagents`.
- The original `UnifiedBags335` addon must be disabled. `BankReagentsUI` and `mod-bank-reagents` are neither used nor required.

## Installation

Copy the inner `UnifiedNativeBags335` directory to:

```text
World of Warcraft/Interface/AddOns/UnifiedNativeBags335/
```

Restart the client or reload the UI. The addon registers itself as the Native Reagents presentation owner, so the stock Native Reagents bank page does not compete with its bank window.

## Migrating from UnifiedBags335

1. Exit the client.
2. Disable or remove the original `UnifiedBags335` addon. Do not load both addons together; UnifiedNativeBags335 detects this and disables itself rather than allowing both to own the same bag and bank frames.
3. Install and enable UnifiedNativeBags335.
4. Keep the existing `WTF` SavedVariables data.

The addon intentionally continues to use `UnifiedBags335DB`. Existing layout settings, window positions, scale, bag-slot preferences, and cached account counts migrate without conversion. Do not delete or rename that SavedVariables table.

## Bank and Reagent Storage

The existing bank window retains its **Bank** and **Reagent Storage** controls. Bank shows physical personal-bank containers. Reagent Storage presents the authoritative virtual quantities returned by `NativeReagents.GetItems()` using the same searchable, scrollable item grid.

Supported reagent interactions:

- Drag a full inventory stack onto the reagent grid to request that exact stack quantity.
- Shift-split an inventory stack and drop it onto the reagent grid to request the selected quantity. The quantity is recorded when the split begins because the 3.3.5a cursor does not reliably expose it.
- **Deposit Reagents** calls `NativeReagents.DepositAll()`.
- Right-click a stored reagent to withdraw one normal item stack.
- Shift-click a stored reagent to choose an exact withdrawal quantity.
- Drag a stored reagent to the Bags window to request a normal-stack withdrawal.
- **Auto Deposit** displays and changes the server-confirmed Native Reagents setting.

Requests are debounced until an authoritative item snapshot or error arrives. The UI never subtracts or adds virtual quantities optimistically. Server failures leave inventory and displayed storage state under the control of Native Reagents.

## Known limitations

- Virtual stored reagents are quantities, not physical slots. Dragging from Reagent Storage requests a withdrawal to normal inventory; it cannot guarantee a particular destination bag slot.
- A deposit drag must originate from an inventory button managed by UnifiedNativeBags335 so the exact full or split quantity can be tracked. Untracked cursor items are rejected instead of guessing a quantity.
- Live banker authorization, bag-space failure messages, and protected cursor behavior require verification in a real 3.3.5a client; repository tests cannot emulate the WoW UI runtime.

## Compatibility

Ordinary inventory, personal bank, guild bank, profession material counts, Have Materials filtering, and remote crafting remain owned by their established implementations. UnifiedNativeBags335 changes only reagent-storage presentation and calls the public Native Reagents operations for deposits, withdrawals, synchronization, and Auto Deposit.
