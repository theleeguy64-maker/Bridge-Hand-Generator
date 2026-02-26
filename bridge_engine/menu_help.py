# bridge_engine/menu_help.py

from __future__ import annotations

from typing import Dict

# Central registry of help text for all menus.
# Add/edit entries here; everything else just calls get_menu_help("some_key").
_MENU_HELP: Dict[str, str] = {
    "main_menu": """\
=== Bridge Hand Generator – Main Menu ===

This is the top-level menu for the whole application.

Options:
  0) Exit
      Quit the program and return to your shell.

  1) Profile management
      Open the Profile Manager. From there you can:
        • List profiles on disk
        • Create new profiles (metadata-only wizard with standard constraints
          pre-attached)
        • View / print full profile details
        • Edit metadata only (name, description, tag, dealer, author,
          version, sort order, rotate flag, NS/EW role / index settings)
        • Edit constraints only (keep metadata, change seat constraints)
        • Delete profiles
        • Save a profile as a new version
        • Work with draft *_TEST.json profiles via Draft Tools

  2) Deal generation
      Run the main deal generator using a chosen profile. Typical flow:
        • Choose a profile
        • Enter owner / player name (for labelling output)
        • Choose base output directory (TXT and LIN are written under this)
        • Choose number of deals to generate
        • Decide whether to use the default seeded run
        • Decide whether to randomly rotate deals (swap N/S and E/W)
      The generator then:
        • Validates the profile
        • Attempts to build the requested number of deals
        • Writes TXT + LIN files
        • Prints a session summary and optional diagnostics.

  3) Admin
      Open the Admin submenu for tools that aren’t core deal generation, such
      as LIN file combination. Use this when you want to post-process or
      inspect outputs, rather than generate new deals from a profile.

  4) Help
      Show this help text describing the main menu and where to go next.

Tips:
  • If you’re unsure where to start, go to "1) Profile management" and
    inspect an existing profile before generating deals.
  • You can always return here from submenus and choose "0) Exit" to quit.
""",
    "admin_menu": """\
=== Bridge Hand Generator – Admin Menu ===

This menu contains tools and utilities that are not part of the core
deal generation flow.

Options:
  0) Exit
      Return to the main menu.

  1) LIN Combiner
      Combine multiple LIN files into a single output file.
      Typical flow:
        • Select one or more source LIN files.
        • Optionally assign integer weights (e.g. 2,1,1) to control how often
          deals from each file appear in the combined output.
        • Choose an output path for the combined LIN file.
      Behaviour notes:
        • Boards in the combined file are re-numbered sequentially (1..N).
        • Weights are relative frequencies; if left blank, each file is treated
          as weight 1.

  2) Recover/Delete *_TEST.json drafts
      Manage draft profile files (created during editing as autosaves).
      Options:
        • Delete a single draft by number
        • Delete all drafts at once
      Draft files end in _TEST.json and sit alongside canonical profiles.

  3) Profile Diagnostic
      Run the v2 deal builder on a chosen profile and print detailed
      failure attribution diagnostics. Useful for analysing which seats
      fail most often and why (shape vs HCP).
      Typical flow:
        - Choose a profile from disk
        - Enter number of boards to diagnose (default 20)
        - View per-board results: shape, HCP, attempt count
        - View aggregate failure attribution table (5 categories x 4 seats)
        - View attempt statistics (total, mean, min, max, wall time)

  4) Help
      Show this help text describing the Admin menu.
""",
    "profile_manager_menu": """\
=== Profile Manager – Overview ===

The Profile Manager is where you define and maintain Hand Profiles.

0) Exit
   Return to the main menu.

1) List profiles
   Show all profiles found in the profiles/ directory.

2) View / print profile (full details)
   Dump full metadata and constraint details for a single profile.

3) Edit profile
   Edit metadata or constraints of an existing profile.

4) Create new profile
   Run the interactive wizard to create a new profile.

5) Delete profile
   Remove a profile JSON file from disk (with confirmation).

6) Save profile as new version
   Copy an existing profile to a new versioned file and optionally
   tweak metadata.

7) Help
   Show this help text.
""",
    "deal_generation_menu": """\
=== Deal Generation – Overview ===

This flow takes a prepared Hand Profile and generates one or more deals.

Typical steps:
  1) Choose a profile
      Select which Hand Profile to use (NS/EW constraints, metadata, etc.).

  2) Enter owner / player name
      A free-text label written into TXT/LIN output (e.g. your name or the
      group the deals are for).

  3) Choose base output directory
      The generator creates subfolders and files under this directory
      for TXT and LIN output.

  4) Enter number of deals
      How many boards you want to generate (e.g. 4, 12, 24).

  5) Seed / rotation options
      – "Use default seeded run?" controls whether a fixed RNG seed is used
        (reproducible run) or a fresh random seed.
      – "Randomly rotate deals?" controls whether deals are randomly rotated
        (swap N/S and E/W) when written.

  6) Generation + output
      The engine:
        – Validates the profile
        – Attempts to build each board respecting constraints, using shape-based
          pre-allocation for tight seats (seats with narrow suit requirements)
        – Retries each board up to 50 times; adaptively re-seeds the RNG if a
          board takes too long (handles difficult constraint combinations)
        – Writes TXT and LIN outputs
        – Prints a session summary with per-board timing, re-seed counts, and,
          if enabled, diagnostics (per-seat success rates, RS usage, etc.).

If generation is interrupted (Ctrl-C), partial diagnostics may still be printed
to help you diagnose constraint tightness or RS behaviour.
""",
    "exclusions": """\
=== Sub-profile Exclusions -- Help ===

Exclusions let you reject specific hand shapes AFTER a hand has passed
the standard constraints for a seat's sub-profile. If a dealt hand
matches an exclusion, the generator discards it and retries.

There are two types of exclusion:

1) SHAPES -- Exclude 4-digit suit-length patterns
   Each shape is 4 digits representing Spades-Hearts-Diamonds-Clubs
   and must sum to 13.

   Exact shapes:
     4333  = exactly 4 spades, 3 hearts, 3 diamonds, 3 clubs
     4432  = exactly 4 spades, 4 hearts, 3 diamonds, 2 clubs
     5332  = exactly 5 spades, 3 hearts, 3 diamonds, 2 clubs

   Wildcard shapes (use 'x' for any digit):
     64xx  = 6 spades, 4 hearts, any diamond/club split
     5xxx  = 5 spades, any distribution in other suits
   Wildcards expand to all matching shapes that sum to 13.

   Enter shapes as comma-separated values (e.g. 4333,64xx).
   A hand matching ANY of the listed shapes is excluded.

2) RULES -- Exclude by suit-group clause (up to 2 clauses, AND logic)
   Each clause has three parts:
     group     = which suits to check:
                   ANY   = all 4 suits (S, H, D, C)
                   MAJOR = majors only (S, H)
                   MINOR = minors only (D, C)
     length_eq = the exact suit length to look for (0-13)
     count     = how many suits in the group must have that length

   Examples:
     MAJOR length_eq=4 count=2
       -> exclude if BOTH majors have exactly 4 cards (4-4 in majors)

     ANY length_eq=3 count=4
       -> exclude if ALL four suits have exactly 3 cards (4333 family)

   With two clauses (AND):
     Clause 1: MAJOR length_eq=4 count=2
     Clause 2: MINOR length_eq=3 count=1
       -> exclude hands with 4-4 majors AND exactly one 3-card minor

Tips:
  - Shapes are simpler but only match exact patterns.
  - Rules are more flexible for families of shapes.
  - Each exclusion targets one sub-profile index on one seat.
  - You can add multiple exclusions per seat.
""",
    "edit_profile_mode": """\
=== Edit Profile – Mode Selection ===

Each profile has two parts: metadata and constraints.

METADATA (option 1) — lightweight edits:
  These are descriptive fields that label and configure the profile:
    • Profile name, description, tag (Opener/Overcaller)
    • Author, version
    • Dealer seat (N/E/S/W)
    • Sort order (custom display numbering in menus)
    • Rotate deals by default (swap N↔S and E↔W randomly)
    • NS role mode (who drives the auction for North–South)
    • EW role mode (who drives the auction for East–West)

  Note: Dealing order is auto-computed at runtime based on constraint
  difficulty — it is not user-editable.

  Editing metadata does NOT re-run the wizard — you just update the
  fields and save.

CONSTRAINTS (option 2) — full wizard re-run:
  Constraints define the actual hand requirements for each seat. Each
  seat has one or more "sub-profiles".

  For each sub-profile, the wizard runs these steps in order:
    1. "Edit Sub-profile N?" — skip prompt (editing existing profiles
       only). Answer No to keep that sub-profile's constraints, role
       usage, AND exclusions entirely unchanged.
    2. Constraints — HCP range, per-suit card-count ranges, and
       optional extra constraint (RS / PC / OC).
    3. Role usage — NS or EW driver/follower tag (only when a driver
       mode is active for that pair).
    4. Exclusions — reject specific shapes or shape families.

  After all sub-profiles are defined:
    5. Weights — how often each sub-profile is selected (must sum to
       100% across all subs for the seat).

  After all SEATS are configured:
    6. Bespoke matching — if a pair (NS or EW) has a fixed driver
       mode and multiple sub-profiles, the wizard offers bespoke
       subprofile matching. For each driver sub-profile, you choose
       which follower sub-profiles can pair with it. This replaces
       the default same-index coupling and allows unequal sub-profile
       counts between paired seats.

  The wizard uses current constraints as defaults so you only change
  what you need.

SUB-PROFILE NAMES (option 3) — quick name edit:
  Give each sub-profile an optional display label (e.g. "Strong opener",
  "Weak variant"). Names appear in menus, viability warnings, and
  diagnostic output. Enter a blank name to clear it.
""",
    "draft_tools": """\
=== Draft Tools – *_TEST.json Files ===

During profile editing, the wizard auto-saves a "draft" copy of your
profile with a *_TEST.json suffix. This is a safety net — if the
editor crashes or you cancel, your in-progress work is preserved in
the draft file.

Over time, draft files can accumulate in your profiles/ directory.
They are NOT used during deal generation (only canonical profiles
are loaded). Deleting them is safe cleanup.

Options:
  1) Delete one draft — choose a specific draft file to remove
  2) Delete ALL drafts — remove every *_TEST.json file at once
  3) Cancel — return without deleting anything
  4) Help — show this help text
""",
    "extra_constraint": """\
=== Extra Constraint – Sub-profile Constraint Mode ===

Every sub-profile has standard constraints (HCP range + per-suit
card-count ranges). Optionally, you can add ONE extra constraint
that links suit selection across seats or across deals.

The four options:

1) STANDARD-ONLY (None)
   No extra constraint — just HCP and suit-length ranges.
   Use this when the seat has fixed, predictable requirements.
   Example: "12–14 HCP, balanced" — no suit-linking needed.

2) RANDOM SUIT (RS)
   Each deal, the generator randomly picks N suit(s) from a list
   you define. The suit-length constraints then apply to whichever
   suit(s) are chosen.

   You configure:
     • How many suits to pick (usually 1)
     • Which suits are allowed (e.g. [S, H] for majors only)
     • A SuitRange per chosen suit (min/max card count + optional HCP)

   Example: "Pick 1 from [S, H] with 6+ cards" means sometimes the
   hand has 6+ spades, sometimes 6+ hearts — decided randomly for
   each board. This models a player who opens 1-of-a-major but you
   don't care which major.

3) PARTNER CONTINGENT (PC)
   This seat's extra constraint depends on what the PARTNER's Random
   Suit chose for the current deal.

   You configure:
     • Which seat is the partner (must have an RS constraint)
     • A SuitRange applied to the partner's chosen suit
     • Optionally: "inverse" mode — target the suit the partner did
       NOT pick instead of the one they picked

   Example (normal): North RS picks Hearts → South PC requires 3+
   hearts (showing support for partner's suit).

   Example (inverse): North RS picks Hearts from [S, H] → South PC
   requires 3+ spades (covering the other major).

4) OPPONENT CONTINGENT-SUIT (OC)
   Same concept as PC, but reacting to an OPPONENT's RS choice.

   You configure:
     • Which seat is the opponent (must have an RS constraint)
     • A SuitRange applied to the opponent's chosen suit
     • Optionally: "inverse" mode — target the non-chosen suit

   Example (normal): West RS picks Spades → North OC requires 4+
   spades (modeling an overcall in the opponent's suit).

   Example (inverse): West RS picks Spades from [S, H] → North OC
   requires 4+ hearts (bidding the other major).

Tips:
  • Only ONE extra constraint per sub-profile (RS, PC, or OC).
  • PC and OC require the referenced seat to have an RS constraint.
  • Inverse mode requires the referenced RS to have exactly 1 suit
    left over after picking (e.g., pick 1 from 2 allowed suits).
""",
    "ns_role_mode": """\
=== NS Role Mode – Who Drives the Auction? ===

When both North and South have multiple sub-profiles, "NS role mode"
controls which seat's sub-profile index is chosen first each board.
The other seat ("follower") then uses the same index, ensuring the
partnership's sub-profiles stay coordinated.

The five modes:

1) NORTH DRIVES — North always drives
   North's sub-profile index is chosen first (by weight), and South
   follows with the same index.
   Use when North is always the "opener" and South's hand should
   match North's hand type.

2) SOUTH DRIVES — South always drives
   South's sub-profile index is chosen first, North follows.
   Symmetric opposite of mode 1.

3) RANDOM_DRIVER — Random driver per board
   Each board, one of N or S is randomly designated as driver.
   The other follows. Use when either player could be opener and
   you want variety.

4) NO_DRIVER — No explicit driver, but index matching applies
   Neither seat is the "driver", but both seats still use the same
   sub-profile index each board. The index is chosen by combined
   weight. Use when the sub-profiles are symmetric between N and S.

5) NO_DRIVER_NO_INDEX — No driver, no index matching
   Each seat's sub-profile is chosen independently. North might use
   sub-profile 0 while South uses sub-profile 2 on the same board.
   This is the simplest and most flexible default — use it unless
   you specifically need coordinated NS sub-profile selection.

Role filtering (active at runtime):
  When a driver mode is selected (modes 1–3), per-sub-profile "role
  usage" tags (any / driver_only / follower_only) control which
  sub-profiles are eligible for the driver and follower. For example,
  a sub-profile tagged "driver_only" will never be selected when the
  seat is the follower.

Bespoke matching (optional, modes 1–2 only):
  After editing constraints, the wizard offers "bespoke subprofile
  matching" for the pair. This replaces the default same-index
  coupling with an explicit map: for each driver sub-profile, you
  choose which follower sub-profiles can pair with it. This allows
  unequal sub-profile counts between paired seats and fine-grained
  control over which combinations are allowed.

Tips:
  • If North and South have DIFFERENT numbers of sub-profiles,
    bespoke matching lets you define exactly which follower subs
    pair with each driver sub (no padding needed).
  • For most profiles (especially when only one seat has multiple
    sub-profiles), mode 5 is the safest choice.
  • Role filtering + bespoke matching can be combined: the driver
    picks from role-eligible subs, then the follower picks from
    the bespoke map entries that are also role-eligible.
""",
    "ew_role_mode": """\
=== EW Role Mode – Who Drives the Auction? ===

When both East and West have multiple sub-profiles, "EW role mode"
controls which seat's sub-profile index is chosen first each board.
The other seat ("follower") then uses the same index, ensuring the
partnership's sub-profiles stay coordinated.

The five modes:

1) EAST DRIVES — East always drives
   East's sub-profile index is chosen first (by weight), and West
   follows with the same index.
   Use when East is always the "opener" and West's hand should
   match East's hand type.

2) WEST DRIVES — West always drives
   West's sub-profile index is chosen first, East follows.
   Symmetric opposite of mode 1.

3) RANDOM_DRIVER — Random driver per board
   Each board, one of E or W is randomly designated as driver.
   The other follows. Use when either player could be opener and
   you want variety.

4) NO_DRIVER — No explicit driver, but index matching applies
   Neither seat is the "driver", but both seats still use the same
   sub-profile index each board. The index is chosen by combined
   weight. Use when the sub-profiles are symmetric between E and W.

5) NO_DRIVER_NO_INDEX — No driver, no index matching
   Each seat's sub-profile is chosen independently. East might use
   sub-profile 0 while West uses sub-profile 2 on the same board.
   This is the simplest and most flexible default — use it unless
   you specifically need coordinated EW sub-profile selection.

Role filtering (active at runtime):
  When a driver mode is selected (modes 1–3), per-sub-profile "role
  usage" tags (any / driver_only / follower_only) control which
  sub-profiles are eligible for the driver and follower. For example,
  a sub-profile tagged "driver_only" will never be selected when the
  seat is the follower.

Bespoke matching (optional, modes 1–2 only):
  After editing constraints, the wizard offers "bespoke subprofile
  matching" for the pair. This replaces the default same-index
  coupling with an explicit map: for each driver sub-profile, you
  choose which follower sub-profiles can pair with it. This allows
  unequal sub-profile counts between paired seats and fine-grained
  control over which combinations are allowed.

Tips:
  • If East and West have DIFFERENT numbers of sub-profiles,
    bespoke matching lets you define exactly which follower subs
    pair with each driver sub (no padding needed).
  • For most profiles (especially when only one seat has multiple
    sub-profiles), mode 5 is the safest choice.
  • Role filtering + bespoke matching can be combined: the driver
    picks from role-eligible subs, then the follower picks from
    the bespoke map entries that are also role-eligible.
""",
    # --- y/n help entries ---
    "yn_non_chosen_partner": """\
=== Partner Contingent – Chosen or Unchosen Suit ===

A Partner Contingent (PC) constraint targets one of the suits from
your partner's Random Suit (RS).

  C = Chosen suit — the suit the partner's RS picked this deal.
  U = Unchosen suit — the suit the partner's RS did NOT pick.

Example:
  North's RS picks 1 suit from [Spades, Hearts].
  If North picks Hearts this board:
    • Chosen (C):   South's PC constraint applies to Hearts
    • Unchosen (U): South's PC constraint applies to Spades

Use unchosen mode when you want the partnership to cover DIFFERENT
suits — e.g., North opens one major and South has length in the
OTHER major.

Requirement: The partner's RS must have exactly 1 unchosen suit
(e.g., pick 1 from 2 allowed suits). If the partner picks 1 from
3+ suits, there would be multiple unchosen suits and unchosen mode
cannot determine which one to target.

Enter C for chosen suit, U for unchosen suit.
""",
    "yn_non_chosen_opponent": """\
=== Opponent Contingent – Chosen or Unchosen Suit ===

An Opponent Contingent (OC) constraint targets one of the suits from
the opponent's Random Suit (RS).

  C = Chosen suit — the suit the opponent's RS picked this deal.
  U = Unchosen suit — the suit the opponent's RS did NOT pick.

Example:
  West's RS picks 1 suit from [Spades, Hearts].
  If West picks Hearts this board:
    • Chosen (C):   North's OC constraint applies to Hearts
    • Unchosen (U): North's OC constraint applies to Spades

Use unchosen mode when you want to model a defensive hand that bids
the suit the opponent did NOT open — e.g., if the opponent opens
Hearts, your hand has length in Spades instead.

Requirement: The opponent's RS must have exactly 1 unchosen suit
(pick 1 from 2 allowed). Multiple unchosen suits are ambiguous
and not supported.

Enter C for chosen suit, U for unchosen suit.
""",
    "yn_edit_weights": """\
=== Sub-profile Weights ===

Each sub-profile has a weight that controls how often it is selected
when generating deals. By default, all sub-profiles have equal weight.

Example: If a seat has 3 sub-profiles with weights 60%, 20%, 20%:
  • ~60% of boards will use sub-profile 1
  • ~20% of boards will use sub-profile 2
  • ~20% of boards will use sub-profile 3

Weights are percentages and must sum to 100%. Use weights when one
hand type is more common than another — for example, if you want
most boards to feature a balanced opener but occasionally include
a strong 2-club hand.

Options:
  0) Exit — keep weights as shown (default)
  1) Keep current weights
  2) Use even weights (equal across all sub-profiles)
  3) Manually define weights (enter percentages that sum to 100%)
""",
    "yn_edit_roles": """\
=== NS Role Usage (Driver / Follower) ===

When both North and South have multiple sub-profiles AND NS role mode
uses a driver/follower system (modes 1–3), each sub-profile can be
tagged with a "role usage":

  • "any" — this sub-profile can be used whether the seat is driving
    or following (default)
  • "driver_only" — only used when THIS seat is the driver
  • "follower_only" — only used when THIS seat is the follower

These tags are enforced at runtime: the deal generator filters
sub-profiles by role before selecting. A "driver_only" sub will
never be chosen when the seat is the follower, and vice versa.

Example: North has 2 named sub-profiles:
  • Sub-profile 1 (Strong opener): driver_only
  • Sub-profile 2 (Responder): follower_only
When North drives, Sub-profile 1 is used; when South drives, North
uses Sub-profile 2.

When combined with bespoke matching, role filtering applies first
(narrowing eligible subs), then bespoke map entries are consulted
to determine follower candidates.

This prompt appears per-subprofile during constraint editing, right
after each sub-profile's constraints are defined.

Most profiles do not need this level of control. Answer No unless
you specifically want different sub-profiles for driving vs following.

Note: A parallel EW Role Usage prompt appears when EW role mode is active.
""",
    "yn_edit_ew_roles": """\
=== EW Role Usage (Driver / Follower) ===

When both East and West have multiple sub-profiles AND EW role mode
uses a driver/follower system (modes 1–3), each sub-profile can be
tagged with a "role usage":

  • "any" — this sub-profile can be used whether the seat is driving
    or following (default)
  • "driver_only" — only used when THIS seat is the driver
  • "follower_only" — only used when THIS seat is the follower

These tags are enforced at runtime: the deal generator filters
sub-profiles by role before selecting. A "driver_only" sub will
never be chosen when the seat is the follower, and vice versa.

Example: East has 2 named sub-profiles:
  • Sub-profile 1 (Strong overcall): driver_only
  • Sub-profile 2 (Responder): follower_only
When East drives, Sub-profile 1 is used; when West drives, East
uses Sub-profile 2.

When combined with bespoke matching, role filtering applies first
(narrowing eligible subs), then bespoke map entries are consulted
to determine follower candidates.

This prompt appears per-subprofile during constraint editing, right
after each sub-profile's constraints are defined.

Most profiles do not need this level of control. Answer No unless
you specifically want different sub-profiles for driving vs following.
""",
    "yn_exclusions": """\
=== Sub-profile Exclusions ===

Exclusions let you reject specific hand shapes AFTER a hand has
passed the standard constraints. If a dealt hand matches an exclusion,
the generator discards it and retries with a new random deal.

Two types of exclusion:
  • Exact shapes: reject specific 4-digit patterns (e.g., 4333 = four
    spades, three of each other suit)
  • Rules: reject by suit-group clause (e.g., reject if both majors
    have exactly 4 cards)

Use exclusions when your standard constraints are correct but allow
some distributions you don't want. For example, you want 12–14 HCP
with a balanced hand but want to exclude the flattest shapes (4333).

This prompt appears per-subprofile during constraint editing, right
after each sub-profile's role usage. Answer Yes to add or edit
exclusions for that sub-profile, No to skip.
""",
    "yn_rotate_deals": """\
=== Rotate Deals ===

Rotation randomly swaps North↔South and East↔West positions for each
board when writing the output. This means the constrained player won't
always sit in the same seat.

Without rotation, if your profile constrains North as the opener, then
North will ALWAYS be the opener in every board. This can create
positional bias — the person sitting North always gets the interesting
hand.

With rotation enabled, the opener might be North on board 1 but South
on board 3, and the defenders might swap between East and West. This
makes practice sessions more realistic and varied.

The profile has a default rotation setting (shown in the prompt). You
can override it for this specific generation run.

Recommended: Yes for practice sessions where you want variety.
""",
}


def get_menu_help(key: str) -> str:
    """
    Return help text for the given menu key.

    If the key is unknown, return a generic placeholder so calling code
    never crashes just because help text is missing.
    """
    return _MENU_HELP.get(
        key,
        "No further help is available for this menu yet.",
    )
