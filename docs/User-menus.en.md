# User-specific menus

[Deutsch](Benutzermenues.md) · **English**

The HA editor supports multiple complete menus with their own titles and
structures. Shared and personal menus can coexist. Complete menus, submenus and
individual entries can be shared with selected HA users.

## Configure menus and access

1. Open **EnigmaHA Companion**. The **Manage menus** overview lists all complete
   menus with their titles. Choose **Create menu** or the copy icon to add another
   menu. Copies receive new IDs and retain their access rules.
2. Reorder menus using the drag handle or arrow icons. The pencil opens the menu's
   entries. **Back to menu management** returns to the overview; changes remain in the draft
   until saved.
3. Edit the title directly in the menu list. Choose the font family and size under
   **Settings → Devices & services → EnigmaHA Companion → Options**; they apply to
   all menus. Existing font settings are retained. No reconfiguration is needed.
4. Open the user icon above the menu entries. For entries and submenus, the user
   icon (`mdi:account-edit`) immediately before the delete icon opens the same
   dialog. Choose the **Access** rule there:

   | Level | Choices |
   | --- | --- |
   | Complete menu | All users, Selected users, Menu disabled |
   | Submenu or entry | Inherit from parent menu, Selected users, Menu disabled |

5. For **Selected users**, choose one or more active HA users. An empty selection
   grants nobody access. Parent restrictions always apply; a child cannot grant
   access through a denied parent.
   Choose **Apply** to update the draft; **Cancel** or Escape discards changes
   made in the dialog.
   Names appear without IDs. People do not own tokens and are not listed
   separately; their linked HA user determines access.
6. In the preview block on the right of the overview, choose **View for user →
   Open preview**. The preview uses the current draft,
   including unsaved changes, and that user's HA entity permissions. Choose
   **Save** to apply the changes.
   A native HA toast confirms saving. Version information, a missing receiver
   connection and unavailable HACS updates are logged only at DEBUG level.

Missing or inactive users remain in existing rules by their internal ID and are
labelled accordingly without showing the ID. Remove those assignments manually if desired; their absence never
grants access to all users.

## Receiver behavior

The HA user of the token stored on the receiver determines the available menus.
Different tokens for the same user produce the same view. Use tokens belonging
to different HA users for different views. Administrator tokens also follow
menu access rules.

One available menu opens directly. Multiple menus appear in the configured
order in a selection menu. If none are available, the receiver displays a
message. Menus emptied entirely by filtering disappear; deliberately empty
menus remain visible.

Access rules and HA entity permissions both apply. Entities without read
permission disappear; missing control permission removes their actions. The
server restricts menus, states and commands to the same user view. Menu rules
do not change access to other HA APIs. An entity may remain available through
another shared entry.

Saved changes apply immediately to new API requests. The receiver display
updates on its next successful refresh. Changing the token or HA address in
the current receiver version immediately clears previous menus and states.

## Existing installations

When the updated integration first loads, it automatically converts the existing
menu into a collection containing one menu shared with all users. Entry IDs,
titles, ordering, appearance and revision are retained, as are the existing HA
entity permissions. Storage remains `.storage/enigmaha_companion.menu`.
No reconfiguration or new tokens are required.

Receiver menu transport remains protocol v1. Older receivers receive filtered
menu trees; existing release/protocol compatibility checks still apply. The new
receiver version adds the no-menu message and immediate clearing on token changes.

The original admin `/config` route remains available for an unrestricted single
menu. Multiple menus or user restrictions return HTTP 409
`configuration_upgrade_required`, preventing older editors or tools from erasing
access rules. Use `/configuration` for these configurations; see the
[protocol](Protocol.en.md).
