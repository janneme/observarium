# General enhancements of the current scope

1. In object search the results have the form

"OBJECT     SELECT_BUTTON OBJECT_INFO_BUTTON  FINDING_PATHS_BUTTON".
Let us remove the SELECT_BUTTON and make the whole line except the buttons act as "select object".
Let us make the icons bigger but at the same time the list of objects found more compact (lower distance between result rows).

2. Currently we are using a symbol of a dot with a short line to the top right
for a double star (in sky view and several other places). Let us introduce a new symbol - a dot and two short parallel
lines to the top right indicating a double star consisting of more than two
visually observable components. Apply it in all places where applicable.

3. The selected object is displayed in the top left corner of the sky view.
Let us change the form how it is displayed:

3a. standard star: STANDARD_STAR_ICON NAME_OR_CAT_NUMBER (mag. MAG)
3b. variable star: VARIABLE_STAR_ICON NAME_OR_CAT_NUMBER (mag. MAG1-MAG2)
3c. double star: DOUBLE_STAR_ICON NAME_OR_CAT_NUMBER (sep. X'', mag. MAG1/MAG2)
    If the system has more than two components, the data mentioned above should
    be shown for the two brightest components only.
3d. DSO: DSO_SYMBOL DSO_CAT_NUMBER "DSO_NAME" (X"xY", mag. MAG)
    (name is just ommited if not available)

The star symbol should be a dot with size approx. 2/3 of the height of letter 'o'
(of the text following the symbol). The same size should be used for the double
star symbol point (the short line or two lines - depending on the nature of the
double star is on top of this size). For variable star this should be the size of
the outer circle. DSO symbols should be the same as used in the sky view.

4. Let us restructure the menu to make it more transparent:
4a. Currently the toggles are overstriken when inactive and at the same time
    its color is darkened. Let us not overstrike it, just change the color.
4b. Let us move the toggles for the daily/nightly mode and for the finder view
    from the menu to the top bar. Keyboard shortcuts must be preserved.
    The icons in the top bar should be in the order: 1. search, 2. finder view
    toggle, 3. daily/nightly toggle, 4. menu. For the finder view toggle
    use a differnt icon - this one from FontAwesome:

```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.3.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 48C337.7 48 352 62.3 352 80L352 98.3C450.1 112.3 527.7 189.9 541.7 288L560 288C577.7 288 592 302.3 592 320C592 337.7 577.7 352 560 352L541.7 352C527.7 450.1 450.1 527.7 352 541.7L352 560C352 577.7 337.7 592 320 592C302.3 592 288 577.7 288 560L288 541.7C189.9 527.7 112.3 450.1 98.3 352L80 352C62.3 352 48 337.7 48 320C48 302.3 62.3 288 80 288L98.3 288C112.3 189.9 189.9 112.3 288 98.3L288 80C288 62.3 302.3 48 320 48zM163.2 352C175.9 414.7 225.3 464.1 288 476.8L288 464C288 446.3 302.3 432 320 432C337.7 432 352 446.3 352 464L352 476.8C414.7 464.1 464.1 414.7 476.8 352L464 352C446.3 352 432 337.7 432 320C432 302.3 446.3 288 464 288L476.8 288C464.1 225.3 414.7 175.9 352 163.2L352 176C352 193.7 337.7 208 320 208C302.3 208 288 193.7 288 176L288 163.2C225.3 175.9 175.9 225.3 163.2 288L176 288C193.7 288 208 302.3 208 320C208 337.7 193.7 352 176 352L163.2 352zM320 272C346.5 272 368 293.5 368 320C368 346.5 346.5 368 320 368C293.5 368 272 346.5 272 320C272 293.5 293.5 272 320 272z"/></svg>
```

4c. The first menu row: toggles for constellation lines, constellation names
    and constellation boundaries. Let us change the icons:
    1. constellation lines - let us use the form of the Cassiopeia constellation
    2. constellation names - same icon as in with a bold "T" letter (T for text)
       accross it
    3. constellation boundaris - same icon as in 1 with a dashed quare around it

4d. Menu second line: toggles for DSO, Solar system, Horizon and FOV circle.
    Change the icons:
      DSO: 2x2 matrix of small individual DSO types: 1st line: globular cluster,
           open cluster, 2nd line: planetary nebula, galaxy
      Solar system: Sun and two orbits with planets, less eliptical (more circle
           than current)
    (icons for horizon and FOV circle are fine)

4f. Menu third line: observations and telescopes:
    For observations use the following icon from FontAwesome:
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--!Font Awesome Free v7.3.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M64 112c-8.8 0-16 7.2-16 16l0 256c0 8.8 7.2 16 16 16l384 0c8.8 0 16-7.2 16-16l0-256c0-8.8-7.2-16-16-16L64 112zM0 128C0 92.7 28.7 64 64 64l384 0c35.3 0 64 28.7 64 64l0 256c0 35.3-28.7 64-64 64L64 448c-35.3 0-64-28.7-64-64L0 128zM160 320a32 32 0 1 1 -64 0 32 32 0 1 1 64 0zm-32-96a32 32 0 1 1 0-64 32 32 0 1 1 0 64zm104-56l160 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-160 0c-13.3 0-24-10.7-24-24s10.7-24 24-24zm0 128l160 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-160 0c-13.3 0-24-10.7-24-24s10.7-24 24-24z"/></svg>
```

and for telescope the following icon:
```
<?xml version="1.0" encoding="utf-8"?><!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
<svg width="800px" height="800px" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg"><path fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round" stroke-width="32" d="M39.93,327.56l-4.71-8.13A24,24,0,0,1,44,286.64l86.87-50.07a16,16,0,0,1,21.89,5.86l12.71,22a16,16,0,0,1-5.86,21.85L72.76,336.35A24.06,24.06,0,0,1,39.93,327.56Z"/><path fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round" stroke-width="32" d="M170.68,273.72,147.12,233a24,24,0,0,1,8.8-32.78l124.46-71.75a16,16,0,0,1,21.89,5.86l31.57,54.59A16,16,0,0,1,328,210.76L203.51,282.5A24,24,0,0,1,170.68,273.72Z"/><path fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round" stroke-width="32" d="M341.85,202.21l-46.51-80.43A24,24,0,0,1,304.14,89l93.29-53.78A24.07,24.07,0,0,1,430.27,44l46.51,80.43a24,24,0,0,1-8.8,32.79L374.69,211A24.06,24.06,0,0,1,341.85,202.21Z"/><line fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round" stroke-width="32" x1="127.59" y1="480" x2="223.73" y2="272.01"/><line fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round" stroke-width="32" x1="271.8" y1="256.02" x2="368.55" y2="448"/></svg>
```

4f. Menu fourth line: Moon quiz, solar system quiz, constellation quiz, DSO quiz
    Change the icons for the quizes - all will have the following form: icon
    of the quiz matter in background (in darker color) and big bold '?' on to of it
    (centered). For moon use the following SVG:
```
<svg id="icon" xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><defs><style>.cls-1{fill:none;}</style></defs><title>asleep</title><path d="M13.5025,5.4136A15.0755,15.0755,0,0,0,25.096,23.6082a11.1134,11.1134,0,0,1-7.9749,3.3893c-.1385,0-.2782.0051-.4178,0A11.0944,11.0944,0,0,1,13.5025,5.4136M14.98,3a1.0024,1.0024,0,0,0-.1746.0156A13.0959,13.0959,0,0,0,16.63,28.9973c.1641.006.3282,0,.4909,0a13.0724,13.0724,0,0,0,10.702-5.5556,1.0094,1.0094,0,0,0-.7833-1.5644A13.08,13.08,0,0,1,15.8892,4.38,1.0149,1.0149,0,0,0,14.98,3Z"/><rect id="_Transparent_Rectangle_" data-name="&lt;Transparent Rectangle&gt;" class="cls-1" width="32" height="32"/></svg>
```

4g. Menu fifth line: Update data, Synchronize, About
    For update data use the following FontAwesome icon:
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512"><!--!Font Awesome Free v7.3.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M256 32c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 210.7-41.4-41.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l96 96c12.5 12.5 32.8 12.5 45.3 0l96-96c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L256 242.7 256 32zM64 320c-35.3 0-64 28.7-64 64l0 32c0 35.3 28.7 64 64 64l320 0c35.3 0 64-28.7 64-64l0-32c0-35.3-28.7-64-64-64l-46.9 0-56.6 56.6c-31.2 31.2-81.9 31.2-113.1 0L110.9 320 64 320zm304 56a24 24 0 1 1 0 48 24 24 0 1 1 0-48z"/></svg>
```
For synchronize the following icon:
```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512"><!--!Font Awesome Free v7.3.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M256 109.3L256 320c0 17.7-14.3 32-32 32s-32-14.3-32-32l0-210.7-41.4 41.4c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3l96-96c12.5-12.5 32.8-12.5 45.3 0l96 96c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L256 109.3zM224 400c44.2 0 80-35.8 80-80l80 0c35.3 0 64 28.7 64 64l0 32c0 35.3-28.7 64-64 64L64 480c-35.3 0-64-28.7-64-64l0-32c0-35.3 28.7-64 64-64l80 0c0 44.2 35.8 80 80 80zm144 24a24 24 0 1 0 0-48 24 24 0 1 0 0 48z"/></svg>
```
("about" icon is fine)

5. When I am in finder view and got to "Record guide to find object". the search results for the path start point have the form "OBJECT    SELECT_ICON".
   Let us remove the select icon and display just the name. Object will be selected by clicking on the name.

6. When defining the path to find object, the following elements are not compatible with the nightly mode:
   finder circle, border of the text "Tap finder to place a point", color of the selected step.

7. In the "Record guide to find object" view, back arrow is too small, misaligned with the
   text that follows and with too big space between the arrow and the text.

8. In finder view if I tap to "Record guide to find object", in the start point
   selection menu the "Cancel" button seems like disabbled. For other items
   ("STAR_STAR (N steps)") display START_STAR in bold and "N steps" in standard
   font weight.

9. If finder view there is a button "Guide to find the object". Change it to
   "Guide to find the object (NUMBER_OF_PATHS_DEFINED)" (first part in bold,
    parenthesis in normal font).

10. In finder view if I go to finding path using "Guide to find the object" I
    get a screen with a finder view where a finding path is drawn. We need
    the following changes in that screen:

    10a. the rendered finder view cannot be neither zoomed nor moved
    10b. currently bellow the finder view there is a text "No paths defined for this object" - this is irrelevant.
    10c. bellow the finder view I need a one-line navigator for the finding steps. It
         should have the following form:

         PREV_STEP_BUTTON STEP_NUMBER/TOTAL_STEPS NEXT_STEP_BUTTON

         PREV_STEP_BUTTON will be disabled in first step and NEXT_STEP_BUTTON
         will be disabled in last step. Step names will follow the same logic
         as in finding path definition. When we move from one step to another
         the finder view should be moved in the same way it moves when we
         select step in path definition (to position determined by the previous
         step).
    10d. To the right of the finding path name there is button "+ Path".
         This button will be replaced by delete button (and there must be
         a confirmation dialog for the delete) - finding paths can only be
         added using the button "Record guide to find object" in finder view.

11. When defining a path to find an object there is a bug. Here is the use case:
    1. I tap on "Record guide to find object"
    2. I select a starting star.
    3. I set an end star for the first step and set multiplier to 2x.
    4. I tap on "Add" for a new step. The finder wiew is centered like if
       the multiplier is set to "1x" - the multiplier is not taken into account.
       
12. When defining a finding path, the title is "START => END". The arrow => (UTF
    character) is too small and misaligned with the text (too low).
