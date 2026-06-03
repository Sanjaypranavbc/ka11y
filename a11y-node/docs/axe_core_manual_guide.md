**axe-core Rules**

What Is Automated vs. What Still Needs Manual Testing

*WCAG 2.1 --- axe-core 4.11 \| Tags: wcag2a, wcag21aa*

+-----------------------+-----------------------+-----------------------+
| **18**                | **64**                | **32**                |
|                       |                       |                       |
| WCAG Criteria Covered | Total axe-core Rules  | Criteria Needing      |
|                       |                       | Manual Test           |
+=======================+=======================+=======================+
+-----------------------+-----------------------+-----------------------+

**About This Document**

This document lists every axe-core rule mapped to its WCAG 2.1 success
criterion (Level A and AA), with a brief explanation of what each rule
checks automatically. For each criterion, a highlighted note explains
what axe-core cannot detect and therefore still requires manual testing.

axe-core performs static analysis --- it validates presence, syntax, and
markup patterns. It cannot observe runtime behaviour, judge the quality
or accuracy of content, test real assistive technology interactions, or
evaluate cross-page consistency. Manual testing with keyboard
navigation, screen readers, and real users is always required to achieve
full WCAG compliance.

  -----------------------------------------------------------------------
  **1.1.1**     **Non-text Content**                        **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ----------------------------------------------------------------------------------
  **Rule ID**                 **What axe-core Checks**           **Still Needs
                                                                 Manual Check?**
  --------------------------- ---------------------------------- -------------------
  **aria-meter-name**         Checks every ARIA meter element    *Verify name is
                              has an accessible name via         descriptive of what
                              aria-label or aria-labelledby.     is being measured*

  **aria-progressbar-name**   Checks every ARIA progressbar      *Verify name
                              element has an accessible name.    describes the
                                                                 progress task
                                                                 meaningfully*

  **image-alt**               Checks \<img\> elements have an    *Verify alt text
                              alt attribute or                   accurately
                              role=none/presentation.            describes image
                                                                 content*

  **input-image-alt**         Checks \<input type=\'image\'\>    *Verify alt text
                              elements have alternative text.    describes the
                                                                 button action, not
                                                                 just the image*

  **object-alt**              Checks \<object\> elements have    *Verify alternative
                              alternative text.                  is meaningful and
                                                                 equivalent*

  **role-img-alt**            Checks elements with role=\'img\'  *Verify the text
                              have accessible text.              equivalent is
                                                                 accurate for the
                                                                 visual content*

  **svg-img-alt**             Checks SVGs with img/graphics role *Verify SVG
                              have accessible text.              description conveys
                                                                 all informational
                                                                 content*

  **⚠ What axe-core Misses:**                                    
  axe-core verifies alt text                                     
  exists but cannot judge if                                     
  it is meaningful or                                            
  accurate. Decorative images                                    
  marked incorrectly, or                                         
  images with vague alt text                                     
  like \'image.png\', will                                       
  pass the tool but fail the                                     
  criterion.                                                     
  ----------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.2.1**     **Audio-only and Video-only (Prerecorded)** **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  --------------------------------------------------------------------------
  **Rule ID**         **What axe-core Checks**           **Still Needs
                                                         Manual Check?**
  ------------------- ---------------------------------- -------------------
  **audio-caption**   Checks \<audio\> elements have     *Verify caption
                      captions via a \<track\> element.  accuracy,
                                                         completeness, and
                                                         synchronisation*

  **⚠ What axe-core                                      
  Misses:** axe-core                                     
  detects missing                                        
  captions on                                            
  \<audio\> but                                          
  cannot verify if a                                     
  transcript actually                                    
  describes the                                          
  content adequately                                     
  or covers all                                          
  spoken information.                                    
  --------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.2.2**     **Captions (Prerecorded)**                  **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  --------------------------------------------------------------------------
  **Rule ID**         **What axe-core Checks**           **Still Needs
                                                         Manual Check?**
  ------------------- ---------------------------------- -------------------
  **video-caption**   Checks \<video\> elements have     *Verify captions
                      captions via a \<track\> element.  are accurate,
                                                         synchronised, and
                                                         complete*

  **⚠ What axe-core                                      
  Misses:** axe-core                                     
  checks if a                                            
  \<track\> element                                      
  is present but                                         
  cannot verify                                          
  caption accuracy,                                      
  synchronisation,                                       
  speaker                                                
  identification, or                                     
  whether non-speech                                     
  audio is described.                                    
  --------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.3.1**     **Info and Relationships**                  **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -----------------------------------------------------------------------------------
  **Rule ID**                  **What axe-core Checks**           **Still Needs
                                                                  Manual Check?**
  ---------------------------- ---------------------------------- -------------------
  **aria-hidden-body**         Checks aria-hidden=\'true\' is not *Verify no partial
                               on the document \<body\>.          aria-hidden is
                                                                  hiding important
                                                                  content*

  **aria-required-children**   Checks ARIA roles requiring child  *Verify dynamic
                               roles contain them (e.g. listbox   children are
                               \> option).                        correctly added at
                                                                  runtime*

  **aria-required-parent**     Checks elements are inside their   *Verify dynamically
                               required parent role.              injected elements
                                                                  are wrapped
                                                                  correctly*

  **definition-list**          Checks \<dl\> contains only \<dt\> *Verify definition
                               and \<dd\> children.               list structure is
                                                                  semantically
                                                                  appropriate*

  **dlitem**                   Checks \<dt\> and \<dd\> are       *Verify terms and
                               inside a \<dl\>.                   definitions are
                                                                  logically paired*

  **list**                     Checks \<ul\>/\<ol\> contain only  *Verify list
                               \<li\> and script/template         content is
                               children.                          genuinely
                                                                  list-like, not
                                                                  misused for layout*

  **listitem**                 Checks \<li\> elements are inside  *Verify list items
                               \<ul\> or \<ol\>.                  are used
                                                                  semantically, not
                                                                  for visual
                                                                  indentation*

  **p-as-heading**             Checks bold/italic \<p\> elements  *Verify headings
                               are not styled to look like        use actual heading
                               headings.                          elements throughout
                                                                  the page*

  **table-fake-caption**       Checks tables with captions use    *Verify table
                               \<caption\> not a cell in the      captions clearly
                               first row.                         describe the table
                                                                  purpose*

  **td-has-header**            Checks data cells in large tables  *Verify headers
                               (\>3x3) have associated headers.   correctly describe
                                                                  the data they
                                                                  relate to*

  **td-headers-attr**          Checks headers attribute on \<td\> *Verify complex
                               only references \<th\> elements in header associations
                               that table.                        are meaningful to
                                                                  screen reader
                                                                  users*

  **th-has-data-cells**        Checks \<th\> and                  *Verify all headers
                               columnheader/rowheader elements    describe actual
                               have associated data cells.        data and none are
                                                                  orphaned*

  **⚠ What axe-core Misses:**                                     
  axe-core validates                                              
  structural markup (lists,                                       
  tables, ARIA roles) but                                         
  cannot verify if visual                                         
  relationships match semantic                                    
  structure, whether heading                                      
  hierarchy is logical, or if                                     
  data tables convey the                                          
  correct relationships to                                        
  screen readers.                                                 
  -----------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.3.4**     **Orientation**                             **Level AA**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ---------------------------------------------------------------------------------
  **Rule ID**                **What axe-core Checks**           **Still Needs
                                                                Manual Check?**
  -------------------------- ---------------------------------- -------------------
  **css-orientation-lock**   Checks CSS does not lock content   *Manually test
                             to portrait or landscape           rotation on a real
                             orientation.                       device or device
                                                                emulator*

  **⚠ What axe-core                                             
  Misses:** axe-core detects                                    
  CSS media query                                               
  orientation locks in                                          
  stylesheets but cannot                                        
  test actual device                                            
  rotation behaviour in a                                       
  real browser or native                                        
  device context.                                               
  ---------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.3.5**     **Identify Input Purpose**                  **Level AA**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -------------------------------------------------------------------------------
  **Rule ID**              **What axe-core Checks**           **Still Needs
                                                              Manual Check?**
  ------------------------ ---------------------------------- -------------------
  **autocomplete-valid**   Checks autocomplete attribute uses *Verify every
                           a valid value from the HTML        personal data field
                           specification.                     has the correct
                                                              autocomplete token
                                                              applied*

  **⚠ What axe-core                                           
  Misses:** axe-core                                          
  validates the                                               
  autocomplete attribute                                      
  value is a valid token,                                     
  but cannot verify it is                                     
  applied to the right                                        
  fields or that all                                          
  personal data input                                         
  fields have it at all.                                      
  -------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.4.1**     **Use of Color**                            **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -------------------------------------------------------------------------------
  **Rule ID**              **What axe-core Checks**           **Still Needs
                                                              Manual Check?**
  ------------------------ ---------------------------------- -------------------
  **link-in-text-block**   Checks links within text are       *Review all
                           distinguished by more than color   color-coded UI
                           alone (e.g. underline, bold).      elements, charts,
                                                              and status
                                                              indicators
                                                              manually*

  **⚠ What axe-core                                           
  Misses:** axe-core only                                     
  checks links in text                                        
  blocks. It cannot detect                                    
  other UI elements ---                                       
  charts, icons, status                                       
  indicators, form                                            
  validation states ---                                       
  that may rely solely on                                     
  color to convey                                             
  information.                                                
  -------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.4.2**     **Audio Control**                           **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ------------------------------------------------------------------------------
  **Rule ID**             **What axe-core Checks**           **Still Needs
                                                             Manual Check?**
  ----------------------- ---------------------------------- -------------------
  **no-autoplay-audio**   Checks \<video\> and \<audio\> do  *Manually verify
                          not autoplay for more than 3       stop/pause/mute
                          seconds without a control to stop  controls are
                          or mute.                           functional and
                                                             keyboard
                                                             accessible*

  **⚠ What axe-core                                          
  Misses:** axe-core                                         
  checks if autoplay                                         
  exceeds 3 seconds but                                      
  cannot verify whether                                      
  the stop, pause, or                                        
  mute control actually                                      
  functions correctly, or                                    
  is keyboard accessible.                                    
  ------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **1.4.12**    **Text Spacing**                            **Level AA**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ---------------------------------------------------------------------------------
  **Rule ID**                **What axe-core Checks**           **Still Needs
                                                                Manual Check?**
  -------------------------- ---------------------------------- -------------------
  **avoid-inline-spacing**   Checks inline style attributes do  *Apply the WCAG
                             not set text spacing properties    text spacing
                             that would block user override.    bookmarklet and
                                                                verify no content
                                                                is lost or
                                                                overlapping*

  **⚠ What axe-core                                             
  Misses:** axe-core detects                                    
  hardcoded inline spacing                                      
  styles that cannot be                                         
  overridden, but cannot                                        
  verify that content                                           
  remains readable and                                          
  functional when a user                                        
  applies custom spacing                                        
  overrides via a                                               
  bookmarklet or stylesheet.                                    
  ---------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.1.1**     **Keyboard**                                **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ----------------------------------------------------------------------------------------
  **Rule ID**                       **What axe-core Checks**           **Still Needs
                                                                       Manual Check?**
  --------------------------------- ---------------------------------- -------------------
  **frame-focusable-content**       Checks \<iframe\>/\<frame\> with   *Manually tab
                                    focusable content do not have      through all iframe
                                    tabindex=-1 blocking keyboard      content to verify
                                    access.                            full keyboard
                                                                       access*

  **scrollable-region-focusable**   Checks scrollable regions without  *Test all custom
                                    mouse-only scroll are keyboard     scrollable widgets
                                    accessible.                        with keyboard only*

  **server-side-image-map**         Checks server-side image maps are  *If client-side
                                    not used (they require a mouse).   maps are used,
                                                                       verify all \<area\>
                                                                       links are keyboard
                                                                       reachable*

  **⚠ What axe-core Misses:**                                          
  axe-core checks iframes and                                          
  scrollable regions but cannot                                        
  test custom widgets ---                                              
  dropdowns, modals, date pickers,                                     
  carousels, drag-and-drop                                             
  interfaces --- for full keyboard                                     
  operability or correct focus                                         
  management.                                                          
  ----------------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.2.1**     **Timing Adjustable**                       **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -------------------------------------------------------------------------
  **Rule ID**        **What axe-core Checks**           **Still Needs
                                                        Manual Check?**
  ------------------ ---------------------------------- -------------------
  **meta-refresh**   Checks \<meta                      *Test all session
                     http-equiv=\'refresh\'\> is not    timeouts and JS
                     used for automatic page refresh or timers --- verify
                     redirect.                          user can extend or
                                                        disable them*

  **⚠ What axe-core                                     
  Misses:** axe-core                                    
  catches \<meta                                        
  refresh\>                                             
  redirects but                                         
  cannot detect                                         
  JavaScript-based                                      
  session timeouts,                                     
  token expiry                                          
  timers, or other                                      
  programmatic time                                     
  limits.                                               
  -------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.2.2**     **Pause, Stop, Hide**                       **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **Rule ID**      **What axe-core Checks**           **Still Needs
                                                      Manual Check?**
  ---------------- ---------------------------------- -------------------
  **blink**        Checks the deprecated \<blink\>    *Review all CSS
                   element is not used.               animations,
                                                      sliders, and GIFs
                                                      for pause/stop
                                                      controls*

  **marquee**      Checks the deprecated \<marquee\>  *Review all
                   element is not used.               auto-moving content
                                                      for controls to
                                                      pause, stop, or
                                                      hide*

  **⚠ What                                            
  axe-core                                            
  Misses:**                                           
  axe-core only                                       
  flags deprecated                                    
  \<blink\> and                                       
  \<marquee\> HTML                                    
  elements. CSS                                       
  animations,                                         
  JavaScript                                          
  carousels,                                          
  auto-advancing                                      
  sliders,                                            
  background                                          
  videos, and                                         
  animated GIFs                                       
  are completely                                      
  invisible to it.                                    
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.4.1**     **Bypass Blocks**                           **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **Rule ID**      **What axe-core Checks**           **Still Needs
                                                      Manual Check?**
  ---------------- ---------------------------------- -------------------
  **bypass**       Checks each page has at least one  *Manually activate
                   mechanism (e.g. skip link) to      skip links and
                   bypass repeated navigation blocks. verify focus moves
                                                      to the correct
                                                      content area*

  **⚠ What                                            
  axe-core                                            
  Misses:**                                           
  axe-core checks                                     
  a skip link                                         
  exists but                                          
  cannot verify it                                    
  actually moves                                      
  keyboard focus                                      
  to the correct                                      
  target, or that                                     
  the skip link is                                    
  visible on                                          
  focus.                                              
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.4.2**     **Page Titled**                             **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ---------------------------------------------------------------------------
  **Rule ID**          **What axe-core Checks**           **Still Needs
                                                          Manual Check?**
  -------------------- ---------------------------------- -------------------
  **document-title**   Checks each HTML document has a    *Verify each page
                       non-empty \<title\> element.       title is unique,
                                                          descriptive, and
                                                          reflects page
                                                          content*

  **⚠ What axe-core                                       
  Misses:** axe-core                                      
  checks the \<title\>                                    
  element is non-empty                                    
  but cannot verify if                                    
  the title is                                            
  descriptive, unique                                     
  across pages, or                                        
  correctly reflects                                      
  the current page                                        
  content.                                                
  ---------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **2.4.4**     **Link Purpose (In Context)**               **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **Rule ID**      **What axe-core Checks**           **Still Needs
                                                      Manual Check?**
  ---------------- ---------------------------------- -------------------
  **area-alt**     Checks \<area\> elements in image  *Verify alt text
                   maps have alternative text.        describes the link
                                                      destination, not
                                                      just the image
                                                      area*

  **link-name**    Checks links have discernible text *Review all links
                   (via content, aria-label, or       for meaningful,
                   aria-labelledby).                  descriptive text
                                                      --- especially
                                                      icon-only links*

  **⚠ What                                            
  axe-core                                            
  Misses:**                                           
  axe-core checks                                     
  links have some                                     
  text, but cannot                                    
  judge whether                                       
  generic phrases                                     
  like \'click                                        
  here\', \'read                                      
  more\', or                                          
  \'learn more\'                                      
  are meaningful                                      
  in context, or                                      
  whether                                             
  aria-label                                          
  overrides                                           
  accurately                                          
  describe the                                        
  destination.                                        
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------
  **3.1.1**     **Language of Page**                        **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  -----------------------------------------------------------------------------------
  **Rule ID**                  **What axe-core Checks**           **Still Needs
                                                                  Manual Check?**
  ---------------------------- ---------------------------------- -------------------
  **html-has-lang**            Checks the \<html\> element has a  *Verify the lang
                               lang attribute.                    value matches the
                                                                  primary language of
                                                                  the page content*

  **html-lang-valid**          Checks the lang attribute uses a   *Verify the
                               valid BCP 47 language code.        language code is
                                                                  correct (e.g.
                                                                  \'en-GB\' not just
                                                                  \'english\')*

  **html-xml-lang-mismatch**   Checks lang and xml:lang           *Verify both
                               attributes agree on the base       attributes reflect
                               language when both are present.    the correct content
                                                                  language*

  **⚠ What axe-core Misses:**                                     
  axe-core validates the lang                                     
  attribute exists and is a                                       
  valid BCP 47 language tag,                                      
  but cannot verify it matches                                    
  the actual language of the                                      
  page content.                                                   
  -----------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **3.3.2**     **Labels or Instructions**                  **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ---------------------------------------------------------------------------------------
  **Rule ID**                      **What axe-core Checks**           **Still Needs
                                                                      Manual Check?**
  -------------------------------- ---------------------------------- -------------------
  **form-field-multiple-labels**   Checks form fields do not have     *Review all forms
                                   more than one label element        for clear
                                   associated.                        instructions,
                                                                      required field
                                                                      markers, and format
                                                                      hints*

  **⚠ What axe-core Misses:**                                         
  axe-core flags duplicate labels                                     
  but cannot verify instructions                                      
  are clear, required field                                           
  indicators are explained, error                                     
  format hints are provided, or                                       
  that label text accurately                                          
  describes what input is needed.                                     
  ---------------------------------------------------------------------------------------

  -----------------------------------------------------------------------
  **4.1.2**     **Name, Role, Value**                       **Level A**
  ------------- ------------------------------------------- -------------

  -----------------------------------------------------------------------

  ------------------------------------------------------------------------------------
  **Rule ID**                   **What axe-core Checks**           **Still Needs
                                                                   Manual Check?**
  ----------------------------- ---------------------------------- -------------------
  **aria-allowed-attr**         Checks ARIA attributes are valid   *Test dynamic ARIA
                                for the element\'s role.           state changes with
                                                                   a real screen
                                                                   reader*

  **aria-braille-equivalent**   Checks aria-braillelabel and       *Verify braille
                                aria-brailleroledescription have a labels are
                                non-braille equivalent attribute.  meaningful to
                                                                   braille display
                                                                   users*

  **aria-command-name**         Checks every ARIA button, link,    *Verify names are
                                and menuitem has an accessible     descriptive and not
                                name.                              duplicated across
                                                                   similar controls*

  **aria-conditional-attr**     Checks ARIA attributes are used as *Test conditional
                                specified for the element\'s role. attributes update
                                                                   correctly on user
                                                                   interaction*

  **aria-deprecated-role**      Checks no deprecated ARIA roles    *Replace deprecated
                                are used.                          roles and retest
                                                                   with screen
                                                                   readers*

  **aria-hidden-focus**         Checks aria-hidden elements are    *Navigate with
                                not focusable and contain no       keyboard only ---
                                focusable children.                verify no hidden
                                                                   elements receive
                                                                   focus*

  **aria-input-field-name**     Checks every ARIA input field has  *Verify input names
                                an accessible name.                clearly describe
                                                                   the expected data
                                                                   entry*

  **aria-prohibited-attr**      Checks ARIA attributes are not     *Retest affected
                                used on roles that prohibit them.  elements with a
                                                                   screen reader after
                                                                   fixes*

  **aria-required-attr**        Checks elements with ARIA roles    *Verify required
                                have all required ARIA attributes  attributes are
                                present.                           populated with
                                                                   meaningful values
                                                                   at runtime*

  **aria-roledescription**      Checks aria-roledescription is     *Verify
                                only on elements with an implicit  roledescription
                                or explicit role.                  values are
                                                                   meaningful to
                                                                   screen reader
                                                                   users*

  **aria-roles**                Checks all role attribute values   *Verify custom
                                are valid ARIA roles.              roles behave as
                                                                   expected with
                                                                   assistive
                                                                   technologies*

  **aria-toggle-field-name**    Checks every ARIA toggle field     *Verify toggle
                                (switch, checkbox, radio) has an   state changes are
                                accessible name.                   announced correctly
                                                                   by screen readers*

  **aria-tooltip-name**         Checks every ARIA tooltip has an   *Verify tooltips
                                accessible name.                   are triggered and
                                                                   announced via
                                                                   keyboard as well as
                                                                   mouse*

  **aria-valid-attr-value**     Checks all ARIA attributes have    *Verify attribute
                                valid values.                      values update
                                                                   correctly during
                                                                   dynamic
                                                                   interactions*

  **aria-valid-attr**           Checks all aria-\* attributes are  *Fix typos and
                                valid ARIA attribute names.        retest entire
                                                                   interactive regions
                                                                   with a screen
                                                                   reader*

  **button-name**               Checks buttons have discernible    *Verify icon-only
                                text via content, aria-label, or   buttons have
                                aria-labelledby.                   meaningful labels
                                                                   for screen reader
                                                                   users*

  **duplicate-id-aria**         Checks IDs used in ARIA and label  *Verify ARIA
                                references are unique on the page. relationships
                                                                   resolve correctly,
                                                                   especially after
                                                                   dynamic content
                                                                   loads*

  **frame-title-unique**        Checks \<iframe\> and \<frame\>    *Verify iframe
                                elements have unique title         titles accurately
                                attributes.                        describe their
                                                                   content purpose*

  **frame-title**               Checks \<iframe\> and \<frame\>    *Verify title
                                elements have an accessible name.  values clearly
                                                                   describe the
                                                                   embedded content*

  **input-button-name**         Checks \<input                     *Verify button
                                type=\'button/submit/reset\'\>     labels clearly
                                elements have discernible text.    communicate their
                                                                   action*

  **label**                     Checks every form input element    *Verify labels are
                                has an associated label.           visible, positioned
                                                                   near their input,
                                                                   and clearly
                                                                   describe expected
                                                                   input*

  **nested-interactive**        Checks interactive controls are    *Test nested
                                not nested inside other            structures with
                                interactive controls.              multiple screen
                                                                   readers to confirm
                                                                   correct
                                                                   announcement*

  **select-name**               Checks \<select\> elements have an *Verify the label
                                accessible name.                   clearly describes
                                                                   the purpose and
                                                                   options of the
                                                                   select field*

  **summary-name**              Checks \<summary\> elements        *Verify summary
                                (inside \<details\>) have          text describes the
                                discernible text.                  hidden content well
                                                                   enough to decide
                                                                   whether to expand*

  **⚠ What axe-core Misses:**                                      
  axe-core covers many ARIA                                        
  misuses statically but cannot                                    
  test dynamic state changes at                                    
  runtime (aria-expanded,                                          
  aria-selected, aria-checked                                      
  updating correctly), or                                          
  verify custom components                                         
  behave correctly with actual                                     
  screen readers like NVDA,                                        
  JAWS, or VoiceOver.                                              
  ------------------------------------------------------------------------------------
