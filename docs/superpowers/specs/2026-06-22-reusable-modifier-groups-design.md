# Reusable And Dish-Specific Modifier Groups

## Goal

Businesses can create reusable modifier templates and attach them to many dishes, while still controlling
which options and prices apply to each dish. A group created inside a dish is dish-specific by default and
only enters the reusable library when the owner explicitly saves it as a template.

## Definitions

- A **template** is a business-level modifier definition intended for reuse.
- A **dish-specific group** is stored with the same normalized definition model but is hidden from the
  template library and attached to one dish.
- A **group definition** owns its internal library name, customer-facing label, selection type, and option
  definitions.
- A **dish assignment** owns required/min/max rules, display order, enabled option subset, option defaults,
  and dish-specific price overrides.

Examples:

- Template `Pizza sizes`, customer label `Size`: `10 in`, `12 in`, `16 in`.
- Template `Beverage sizes`, customer label `Size`: `250 ml`, `500 ml`, `1 L`.
- Template `Burger patties`, customer label `Patties`: `Single`, `Double`.
- Dish-specific group `Extras`: `Extra cheese` for one burger.

Pizza and beverage sizes remain separate templates because their units and option sets are different, even
though both use the customer-facing label `Size`.

## Data Model

- `modifier_groups` owns `business_id`, internal `name`, customer-facing `display_name`, `select_type`, and
  `is_template`.
- `modifier_options` owns reusable option labels, suggested `price_delta`, suggested default state, and order.
- `product_modifier_groups` assigns a group to a product and owns required/min/max/order.
- `product_modifier_option_prices` records the options enabled for one assignment. Presence means enabled; absence
  means unavailable for that dish. It also owns `price_delta_override` and the dish-specific default state.
- Every table remains tenant-scoped with `business_id`.
- A template option added later is not automatically enabled on existing dishes.

Effective option pricing is:

`dish base price + (dish override when present, otherwise template option price delta)`

## Dish Behavior

- Attaching a template initially enables its current options and copies its suggested defaults.
- Owners can disable irrelevant options per dish and override prices per dish.
- A normal burger may enable both `Single` and `Double` patties.
- A fixed double-patty burger should normally include double patties in its base product and omit the modifier.
  If structured order data is required, the assignment may enable only `Double`; the ordering UI auto-selects
  the sole required option and does not show a redundant customer choice.
- Optional single add-ons use a multi-select group and render as checkboxes, for example `Extra cheese +R100`.

## API And Transactions

- Template CRUD remains tenant-scoped under `/businesses/{business_id}/modifier-groups`.
- Product create/update accepts either an existing template/group ID or an inline new group definition.
- Inline group creation and product assignment happen in one database transaction. A failed product save must
  not leave an orphan group.
- Product updates reconcile existing assignments in place instead of deleting and reinserting matching rows;
  this avoids the unique `(product_id, modifier_group_id)` collision.
- Order validation accepts only options explicitly enabled for that product assignment.
- Order pricing remains server-authoritative and uses the effective per-dish delta.

## Menu UX

- `Use template` attaches an existing reusable template.
- `Add dish option` creates a dish-specific group.
- Dish-specific groups can be promoted with `Save as template`.
- Shared template names/options are managed through a visible template manager. Dish assignments only edit
  availability, defaults, required/min/max, and dish-specific prices.
- Removing a template from a dish only detaches it.
- Deleting an attached template is blocked until it is detached from affected dishes.
- Misleading reorder grips, reorder text, and collapse controls are removed until reorder/collapse behavior is
  actually implemented.

## Failure Handling

- Product and inline-group writes are atomic.
- Validation errors identify the invalid group or option.
- Template deletion reports that attached dishes must be updated first.
- Non-template groups with no remaining assignments are cleaned up by product update/delete flows.

## Verification

- Backend tests cover inline dish-specific creation, atomic rollback, safe updates retaining existing groups,
  enabled option subsets, price overrides, required/default validation, order pricing, cleanup, and tenant
  isolation.
- Frontend tests cover payload mapping, template attachment, dish-specific defaults, promotion, template
  management requests, and removal of dead controls.
- Backend tests, frontend tests, lint, build, and migration upgrade/downgrade checks run before completion.
- Browser-based visual verification is intentionally excluded at the user's request; the user will verify the
  rendered UI manually.
