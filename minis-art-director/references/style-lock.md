# **Style Lock**

One style lock per set, pasted verbatim into every prompt in that set. Cohesion across the sheet is what separates a set that looks made from a set that looks scraped.

# **Anatomy**

Four to six clauses, always in this order:

1. **Technique** – "digital painting", "Inked comic", "gouache", "clean vector"  
2. **Line** – "crisp dark outline", "no outline, form read by value"  
3. **Lighting** – "flat front lighting, no cast shadow" (safest for minis)  
4. **Saturation** – "muted earth palette", "high-chroma"  
5. **Detail level** – "bold simplified shapes, readable at thumbnail size"  
6. *(optional)* **Era/genre** – "grimdark low fantasy", "storybook high fantasy"

# **Three House Styles**

## **Module Art**

Digital painting in the style of a classic tabletop rulebook illustration. Crisp dark outline, warm muted earth palette, flat front lighting with no cast shadow, bold simplified forms readable at thumbnail size, matte finish.

Best default. Matches printed adventure modules and holds up at 22 mm.

## **Inked**

Bold black ink linework with flat spot colour, heavy outlines, limited four-colour palette, no gradients, flat front lighting, high contrast, silhouette-first design.

Prints beautifully on a cheap laser printer and survives being photocopied. Best choice if the user has no colour printer.

## **Storybook**

Soft gouache illustration, visible brush texture, warm pastel palette, gentle front lighting with no cast shadow, rounded friendly forms, clear silhouette.

Good for friendly creatures and games with kids at the table.

# **Rules**

* Never vary the lock inside a set. Cohesion beats individual beauty.  
* Lighting stays front and flat. Dramatic side lighting produces a dark edge that reads as a printing error once cut out.  
* No cast shadow, ever. A shadow on the ground becomes a grey smudge on the printed base.  
* Push a creature's own glow into the subject clause, not the lock. A flameskull is "wreathed in green flame"; the lighting clause stays as-is.  
* Silhouette first. At 28 mm, colour and texture vanish and only the outline survives. If the user complains minis are hard to tell apart, the fix is more distinct silhouettes, not more detail.

# **Palette Discipline**

Take the palette from `creatures.json` (`[primary, shadow, accent]`) and name the colours in the prompt. Then give each creature type one dominant hue that nothing else in the set uses, so a player can find "the orcs" in a crowded encounter at a glance. That is what the coloured base band is for too.

# **Pose Variants**

For goblin-2, goblin-3, change only the Pose clause:

* "mid-stride, weapon low"  
* "crouched, shield raised"  
* "lunging forward, weapon overhead"  
* "standing alert, weapon at rest"

Keep every other clause byte-identical. Nine skeletons should differ in stance, not in style, palette, or scale.

# **Prompt Template**

\<style lock\> 

Subject: \<expanded creature descriptor\> 

Pose: \<one specific readable action\> 

Framing : full body, standing, feet flush with the bottom edge of the image, centred , entire figure inside frame, no cropping, no zoom 

Background : fully transparent, no ground , no shadow , no scene , no vignette 

Exclusions: no text, no logo, no frame, no border, no base, no plinth, no ground shadow, no watermark 

# **Common Failures and Their Fix**

| Symptom | Cause | Fix |
| :---- | :---- | :---- |
| mini floats above its base | feet not at the frame edge | strengthen the Framing clause; crop the file so feet touch the bottom |
| grey smear on the base | cast shadow in the art | regenerate with "no shadow"; `--strip-bg` will not save you |
| wings/legs cut off at the cut line | limbs left the frame | "entire figure inside frame", wings folded |
| unreadable at print size | too much fine detail | "bold simplified shapes, silhouette-first" |
| sheet looks incoherent | style lock varied between creatures | regenerate the whole set with one lock |
