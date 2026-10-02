# Size and scale

## The table

| Size | Grid | Base width | Base depth | Figure height (heroic) | Figure height (true) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Tiny | 2½ ft | 12.7 mm | 9 mm | 14 mm | 7 mm |
| Small | 5 ft | 25.4 mm | 12.7 mm | 22 mm | 18.7 mm |
| Medium | 5 ft | 25.4 mm | 12.7 mm | 30 mm | 28 mm |
| Large | 10 ft | 50.8 mm | 18 mm | 50 mm | 46.7 mm |
| Huge | 15 ft | 76.2 mm | 18 mm | 72 mm | 70 mm |
| Gargantuan | 20 ft | 101.6 mm | 18 mm | 95 mm | 93.3 mm |

Base width is derived, not chosen: 5 ft = 1 inch on a standard battle grid, so Medium = 25.4 mm. Figure height is a taste call – the defaults are the 28–32 mm "heroic" scale that store-bought minis use, so these sit correctly next to plastic figures.

## Frames: fixed cell, floating art

Every size class has ONE frame – the grid square wide by the class height tall – and the cut rectangle is identical for every creature in that class:

| Class | Frame (mm) | Clip |
| :--- | :--- | :--- |
| Tiny | 19.0 x 48 | 3/4" |
| Small | 27.0 x 64 | 3/4" |
| Medium | 27.0 x 80 | 1" |
| Large | 52.4 x 120 | 2" |
| Huge | 77.8 x 164 | 3" |
| Gargantuan | 103.2 x 210 | 4" |

The artwork is shrunk to fit inside that frame preserving aspect, never scaled up. A wide pose (ooze, spider, spread wings) fills the width and is short; a tall narrow one (giant, treant) fills the height and is narrower. The leftover is blank paper above the head.

Two consequences worth stating: cells in a row are identical so the sheet guillotines both ways, and nothing can print taller than the class above it. Before this, a Large owlbear computed to 78 mm – taller than a Huge.

`--size-by area` equalises printed area instead; `--size-by height` restores the original fixed-height behaviour, where same-class widths varied over 2x.

## Scale modes

* **heroic** (default) – the table above. Size classes read clearly at a glance and a Medium mini matches a 28 mm figure.
* **true** – `height_ft × 4.667 mm`. Strictly linear. Honest, and it makes a dragon genuinely intimidating, but a Tiny creature lands at 7 mm and is miserable to cut. Good for a display piece, bad for a stirge swarm.
* **token** – every figure the same height (`--token-mm`, default 28). Base widths still vary, so footprints stay correct. This is the flat-token look: fastest to cut, best for a horde you will lose half of.

## Overriding

Per roster line, as a trailing comment:

```

1 Venomfang (Young Green Dragon)  \# size=huge
4 Giant Spiders                   \# height\_mm=40
1 Ogre                            \# base\_mm=50.8 base\_depth\_mm=16
1 Tiny Winged Thing               \# size=tiny archetype=insectoid

```` 

Per campaign, in `<out>/creatures.local.json`, which is merged over the shipped database:

```json
{
  "creatures": {
    "shadow hound": {
      "size": "medium",
      "archetype": "quadruped",
      "palette": [
        "#2b2b33",
        "#14141a",
        "#6b8ad6"
      ],
      "art": "spectral hound, smoke-edged, blue witchlight eyes",
      "aliases": {
        "hound of the mere": "shadow hound"
      }
    }
  }
}

````

## Size sources

Sizes in `creatures.json` come from the 5e SRD / *Lost Mine of Phandelver* stat blocks. The ones worth double-checking because people guess wrong:

  * Goblin and Twig Blight are **Small**, not Medium.
  * Bugbear and Hobgoblin are **Medium**, despite bugbears being described as hulking.
  * Stirge and Flameskull are **Tiny**.
  * Giant Spider, Ogre, Owlbear, Ochre Jelly and a young green dragon are **Large**. An adult green dragon is Huge – Venomfang is the young one.
  * Spectator is **Medium**; it is beholderkin, not a beholder.
  * Nothic and Grick are **Medium**.

Where the table and your table disagree, your table wins. Override it.

## Aspect ratios

`ARCHETYPE_ASPECT` in `sizes.py` gives the assumed width/height per body type, used for the procedural art and as the presumed bounding box before a supplied image has been measured. Supplied raster art is measured for real: its alpha channel is trimmed to a bounding box, and the true aspect is used. That is why `--strip-bg` matters for art with an opaque background – without transparency there is no bounding box, so the figure's real proportions are unknown.

 