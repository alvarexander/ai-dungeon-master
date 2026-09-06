# Dice

**Read this when** you are touching the dice tray, the 3D die, or the rolling
rules.

---

## Why there are dice at all

The Dungeon Master calls for checks — "make a Dexterity (Stealth) check" — and
without dice the player either invents a number or asks the AI to roll for
them. Both are unsatisfying. Half the pleasure of the game is that the dice
decide, and that nobody at the table, including whoever is running it, knows
what is about to happen.

So the roll happens visibly, and the result is sent to the Dungeon Master as a
sentence it can react to:

> I roll d20+3 with advantage and get 20 (rolled 17; discarded 4).

That last part is what makes this a feature rather than a widget. A dice roller
that does not feed the game is a toy beside it.

---

## The split: rules here, theatre there

| File                           | Job                                                 |
| ------------------------------ | --------------------------------------------------- |
| `core/dice/dice.ts`            | The rules. Pure functions, no browser, no animation |
| `core/dice/polyhedra.ts`       | The shapes. Where every face of every die goes      |
| `features/dice/dice-roller.ts` | The tray: which die, how many, advantage            |
| `features/dice/die-3d.ts`      | The tumbling die                                    |

**The result is decided the instant the button is pressed.** The animation that
follows is presentation. That ordering matters for a reason worth stating: if
the number were chosen when the animation ended, a slow device would change the
odds. It also means the rules and the shapes are testable without a browser,
which is why there are 29 tests for them and none of them render anything.

---

## The rules

### Rolling

`roll(die, { count, modifier, mode })` returns everything about the roll,
including the dice that did not count.

**Randomness comes from `crypto.getRandomValues`**, not `Math.random`. Not
because a dice roll needs cryptographic security, but because dice are the one
thing in a game people will swear feels rigged, and the stronger source costs
nothing and removes the argument.

The modulo is **rejection-sampled**. Taking `random % 20` directly makes the low
faces very slightly more likely, because 2³² is not divisible by 20. The
rejection loop discards the unfair tail. It runs about once in fifty million
rolls, and it means every face is exactly equally likely rather than nearly so.

### Advantage and disadvantage

The fifth-edition rules' way of saying "this is easier than usual" or "harder
than usual": roll two d20 and take the better or the worse.

Three things the implementation gets right, each of which is easy to get wrong:

**Both dice are kept.** `discarded` holds the one that did not count, and the
interface shows it struck through. Seeing the 3 you dodged is most of the
pleasure of advantage; hiding it makes the mechanic feel arbitrary.

**It is a d20 concept only.** There is no such thing as rolling damage with
advantage, so `roll` ignores the mode for other dice and the toggle disappears
from the interface rather than sitting there doing nothing.

**It is exactly two dice**, so the "how many" control is hidden while it is on.

### Criticals

A natural 20 is only a natural 20 on **a single d20**. Rolling eight d6 for a
fireball and seeing a 20 in the total is not a critical hit, and the code
checks `die === 'd20' && count === 1` rather than looking at the total.

---

## The 3D die

Built from ordinary elements placed in space with CSS
`transform-style: preserve-3d`. The browser does the perspective, the rotation
and the depth sorting. **There is no 3D library.**

A library would draw a more exact die and add several hundred kilobytes to a
bundle that is currently under a hundred, for a decoration that is on screen
for a second. That is the wrong trade here.

### Every die is its real shape

A d20 that is not an icosahedron is not a d20. Players know these shapes by
sight, and a stand-in reads as wrong immediately — even to someone who could
not say what is wrong with it.

| Die  | Solid                    | Faces | Shape of a face |
| ---- | ------------------------ | ----- | --------------- |
| d4   | tetrahedron              | 4     | triangle        |
| d6   | cube                     | 6     | square          |
| d8   | octahedron               | 8     | triangle        |
| d10  | pentagonal trapezohedron | 10    | kite            |
| d12  | dodecahedron             | 12    | pentagon        |
| d20  | icosahedron              | 20    | triangle        |
| d100 | pentagonal trapezohedron | 10    | kite            |

A "solid" here just means a three-dimensional shape with flat sides. The names
are the traditional Greek ones and say what they mean: a dodecahedron is a
twelve-sided shape, an icosahedron a twenty-sided one.

The d10 is the interesting one. Its faces are **kites** — four-sided, and
lopsided rather than square — which is why the edge running round the middle of
a d10 zig-zags instead of lying flat. No amount of rotating a regular shape
produces a kite, so the faces are cut from their real corners rather than
stamped from a template.

### Only the corners are written down

`core/dice/polyhedra.ts` contains the corners of each solid and nothing else.
Which corners form a face, which way each face points, what shape it is, where
its number sits — all of it is worked out from those corners.

The rule that makes this possible: **on a shape that bulges outwards rather
than caving in, a face is any flat plane through three corners that no other
corner pokes through.** Every die is such a shape, so trying each group of
three corners and keeping the planes that nothing sticks out past finds every
face, and only the real ones.

The alternative is a hand-typed table of twenty triples for an icosahedron and
twelve five-tuples for a dodecahedron, where one transposed digit gives a shape
that is subtly wrong in a way nobody can debug by looking at it. This file
originally took an even shorter cut — reusing one solid's corners as another's
face directions, which is true of _some_ pairs of solids in _some_ orientations
and was quietly false here. The tests caught it. The corners are the single
source of truth now, because they are the one thing that can be checked against
a reference by eye.

### The numbers are on the faces, and the die lands on the right one

Each face carries its number, and when the tumble finishes the die **turns so
the number it rolled is facing you**, the way a real die comes to rest. Undoing
a face's own two turns, in the opposite order, points it back at the camera —
which is all `restingTransform` does.

Two details copied from real dice:

- **Opposite faces add up to one more than the number of sides.** 1 is across
  from 6 on a d6 and across from 20 on a d20. Manufacturers do it to keep the
  weight even; it is also visible, and a d20 with 19 beside 20 looks wrong to
  anyone who has held one. A tetrahedron has no opposite faces and is numbered
  in order instead.
- **6 and 9 are underlined**, because they are the same glyph turned around.

The **total** is shown beside the die rather than on it. A d20 with a +3
modifier can total 23, and there is no face 23 to land on.

One honest exception: a real d4 has no face pointing up, so it is printed with
three numbers per face and read at the apex. This one puts a single number in
the middle of each face instead. The shape is right and the result is right;
the printing convention is simplified.

### Shading

Facets that are all one colour make a d20 read as a flat blob. Each face is
tinted by how squarely it faces an imaginary light above and to the left, which
is what makes the shape legible while it is spinning.

That calculation lives in `die-3d.ts` rather than `polyhedra.ts`, because
lighting is a matter of taste and geometry is not.

### The tumble

`@keyframes tumble` in `die-3d.scss`. Fast and loose early so it reads as
thrown. While it runs it overrides the die's inline transform; when it ends the
class comes off, the inline transform takes over, and a CSS `transition`
carries the die smoothly round to the face it landed on.

`TUMBLE_MS` in `dice-roller.ts` must match the animation duration. They are two
numbers that have to agree; if the die keeps spinning after the result appears,
that is why.

**Reduced motion shortens the tumble rather than removing it.** A die that does
not move at all is just a number appearing, and the roll appears not to have
happened.

---

## Testing

`core/dice/dice.spec.ts` (13 tests) and `core/dice/polyhedra.spec.ts` (16),
none of which need a browser.

On the rules:

- **Every face of a d20 is reachable.** 4,000 rolls must produce all 20 values.
  A die that never rolls a 20 is broken, and this is the cheapest way to catch
  an off-by-one in the modulo.
- **Advantage really takes the higher**, checked over 200 rolls rather than
  once.
- **The modifier is applied once, not once per die.** `3d6+5` is easy to
  implement as `+5` three times.
- **Advantage is ignored on non-d20 dice.**
- **A critical is only flagged on a single d20.**

On the shapes — these are the kind of thing that looks almost right when it is
wrong, so the properties that make a solid a solid are checked directly rather
than left to the eye:

- **Every die has the number of faces its name promises.** A d20 with nineteen
  faces is the reason `polyhedra.ts` exists.
- **Every face has the right number of corners** — triangles for the d4, d8 and
  d20, squares for the d6, kites for the d10, pentagons for the d12.
- **Every face of a die is the same size and the same distance from the
  centre.** If the derivation picks up a stray corner, one face comes out
  bigger, and this is what notices. It is the test that caught the original
  wrong-shapes bug.
- **Roll a 17, see the 17** — checked for every face of every die.
- **Opposite faces add up to one more than the number of sides.**

---

## Adding a die

1. Add it to `DieType` and `DIE_SIDES` in `core/dice/dice.ts`.
2. Add it to `DIE_TYPES`, which is the order the picker shows.
3. Add its **corners** to `CORNERS` in `core/dice/polyhedra.ts`, centred on the
   origin. Nothing else about the shape needs describing — the faces, their
   directions, their outlines and their numbering are all derived.
4. If it is numbered unusually, add a case to `labelFor` and a matching one to
   `faceIndexFor`. The d10 and d100 are the existing examples.

Then add it to the `EXPECTED` table in `polyhedra.spec.ts`, which is how you
find out whether the corners were right.

---

## Related documents

- [UI_PATTERNS.md](UI_PATTERNS.md) — the design system and animation rules.
- [VOICE_INPUT.md](VOICE_INPUT.md) — the other half of the play screen.
- [ARCHITECTURE.md](ARCHITECTURE.md) — where this sits.
- [TESTING.md](TESTING.md) — the suite as a whole.
