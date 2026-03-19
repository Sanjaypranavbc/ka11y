'use strict';

/**
 * Testing guide for every axe-core rule reachable by this API.
 *
 * Each entry contains:
 *   successCriteriaId — WCAG SC number (null for best-practice-only rules)
 *   wcagLevel         — "A" | "AA" | "AAA" | "best-practice"
 *   title             — short human-readable rule name
 *   guidance          — what the rule checks and why it matters
 *   howToTest         — manual / automated testing steps
 *   failExample       — minimal HTML that triggers the violation
 *   passExample       — corrected HTML that passes
 *   fixTip            — concise remediation advice
 */
const rulesGuide = {

  'accesskeys': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Accesskey Uniqueness',
    guidance: 'Accesskey values must be unique across the whole page. Duplicate accesskeys create ambiguity for keyboard users — the browser resolves the conflict differently per platform and the intended shortcut may not fire.',
    howToTest: 'Search the page HTML for accesskey attributes and confirm each value appears only once.',
    failExample: `<button accesskey="a">Button 1</button>
<a href="#" accesskey="a">Link</a>`,
    passExample: `<button accesskey="a">Button 1</button>
<a href="#" accesskey="b">Link</a>`,
    fixTip: 'Assign a unique character to each accesskey attribute. Consider whether accesskeys are necessary at all, as they can conflict with browser or screen reader shortcuts.',
  },

  'area-alt': {
    successCriteriaId: '2.4.4',
    wcagLevel: 'A',
    title: 'Area Alternative Text',
    guidance: '<area> elements inside image maps act as links and must have an alt attribute that describes the link destination, so screen reader users understand where each area leads.',
    howToTest: 'Inspect every <area> element. Each must have a non-empty alt attribute that describes its purpose or destination.',
    failExample: `<img src="map.png" usemap="#nav" alt="Navigation map">
<map name="nav">
  <area shape="rect" coords="0,0,50,50" href="home.html">
</map>`,
    passExample: `<img src="map.png" usemap="#nav" alt="Navigation map">
<map name="nav">
  <area shape="rect" coords="0,0,50,50" href="home.html" alt="Home">
</map>`,
    fixTip: 'Add a descriptive alt attribute to every <area> element. If the area is purely decorative, use alt="".',
  },

  'aria-allowed-attr': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Attribute Allowed for Role',
    guidance: 'Every ARIA attribute used on an element must be permitted for that element\'s role. Using an invalid attribute (e.g. aria-checked on a link) causes assistive technology to ignore or misinterpret the element.',
    howToTest: 'For each element with ARIA attributes, verify the attribute is listed as allowed for the element\'s implicit or explicit role in the ARIA specification.',
    failExample: `<!-- aria-checked is not valid for role="link" -->
<a href="#" aria-checked="true">Selected link</a>`,
    passExample: `<!-- aria-pressed is valid for role="button" -->
<button aria-pressed="true">Active</button>`,
    fixTip: 'Remove attributes that are not allowed for the element\'s role, or change the role to one that supports the attribute you need.',
  },

  'aria-allowed-role': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'ARIA Role Allowed for Element',
    guidance: 'An element\'s explicit ARIA role must be appropriate for that HTML element. For example, giving an <input type="text"> a role of "heading" is invalid and misleads assistive technology.',
    howToTest: 'For every role attribute, verify it is listed as allowed for that HTML element in the ARIA in HTML specification.',
    failExample: `<label for="r">Name</label>
<input type="text" id="r" role="heading">`,
    passExample: `<label for="r">Name</label>
<input type="text" id="r">`,
    fixTip: 'Remove the role attribute or replace it with one that is valid for the host element.',
  },

  'aria-braille-equivalent': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Braille Label Equivalent',
    guidance: 'When aria-braillelabel or aria-brailledescription is used, a non-braille equivalent (aria-label or aria-description) must also be present so non-braille AT users receive a meaningful name.',
    howToTest: 'Find every element with aria-braillelabel or aria-brailledescription and confirm a matching aria-label or aria-description is also present.',
    failExample: `<button aria-braillelabel="sv">Save</button>`,
    passExample: `<button aria-label="Save" aria-braillelabel="sv">Save</button>`,
    fixTip: 'Always pair aria-braillelabel with aria-label and aria-brailledescription with aria-description.',
  },

  'aria-command-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Command Accessible Name',
    guidance: 'Elements with role="link", "button", "menuitem", "menuitemcheckbox", or "menuitemradio" must have an accessible name so screen reader users know what the control does.',
    howToTest: 'Activate the screen reader and navigate to the element. Confirm the announced name is meaningful.',
    failExample: `<span role="link" tabindex="0"></span>
<span role="menuitem"></span>`,
    passExample: `<span role="link" tabindex="0" aria-label="Go to home page">Home</span>
<span role="menuitem">Settings</span>`,
    fixTip: 'Provide visible text, aria-label, or aria-labelledby on every element with a command role.',
  },

  'aria-conditional-attr': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Conditional Attribute',
    guidance: 'Some ARIA attributes (e.g. aria-checked, aria-expanded) are only valid on specific roles or under specific conditions. Using them incorrectly produces invalid semantics.',
    howToTest: 'Review every conditional ARIA attribute and confirm it is used on a role that supports it and in a context where it is applicable.',
    failExample: `<!-- aria-checked is conditional: only valid on checkbox/radio/switch etc. -->
<select aria-checked="true"><option>A</option></select>`,
    passExample: `<input type="checkbox" aria-checked="true">`,
    fixTip: 'Only apply conditional ARIA attributes when the host element\'s role supports the attribute.',
  },

  'aria-deprecated-role': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Deprecated ARIA Role',
    guidance: 'Deprecated ARIA roles (e.g. "directory", "presentation" on focusable elements) may not be supported by modern assistive technology and should be replaced with current equivalents.',
    howToTest: 'Search for deprecated role values and replace them with supported alternatives.',
    failExample: `<div role="directory">Link list</div>`,
    passExample: `<div role="list">Link list</div>`,
    fixTip: 'Replace deprecated roles with their current equivalents as specified in the WAI-ARIA specification.',
  },

  'aria-dialog-name': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'ARIA Dialog Accessible Name',
    guidance: 'Dialog and alertdialog elements must have accessible names so screen reader users understand the purpose of the dialog when it receives focus.',
    howToTest: 'Open the dialog with a screen reader and confirm a meaningful name is announced.',
    failExample: `<div role="dialog">
  <p>Are you sure?</p>
</div>`,
    passExample: `<div role="dialog" aria-labelledby="dlg-title">
  <h2 id="dlg-title">Confirm Delete</h2>
  <p>Are you sure?</p>
</div>`,
    fixTip: 'Add aria-label or aria-labelledby pointing to a visible heading inside the dialog.',
  },

  'aria-hidden-body': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'aria-hidden on Body',
    guidance: 'Adding aria-hidden="true" to the <body> element hides the entire page from screen readers, making the page completely inaccessible.',
    howToTest: 'Check that the <body> element does not have aria-hidden="true".',
    failExample: `<body aria-hidden="true">
  <main><p>Content</p></main>
</body>`,
    passExample: `<body>
  <main><p>Content</p></main>
</body>`,
    fixTip: 'Remove aria-hidden from the <body> element. If you want to hide a specific region, apply aria-hidden only to that container.',
  },

  'aria-hidden-focus': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Focusable Element Inside aria-hidden',
    guidance: 'Keyboard-focusable elements inside an aria-hidden container are reachable by Tab but invisible to screen readers, causing confusion — the user can focus an element that produces no announcement.',
    howToTest: 'Tab through the page with a screen reader. Confirm no focusable element is silently skipped due to aria-hidden.',
    failExample: `<div aria-hidden="true">
  <button>Click me</button>
</div>`,
    passExample: `<!-- Option 1: Remove aria-hidden so the button is accessible -->
<div>
  <button>Click me</button>
</div>

<!-- Option 2: Make the button unfocusable if the region should be hidden -->
<div aria-hidden="true">
  <button tabindex="-1">Click me</button>
</div>`,
    fixTip: 'Either remove aria-hidden from the container, or add tabindex="-1" to all focusable descendants so they cannot be tabbed to.',
  },

  'aria-input-field-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Input Field Accessible Name',
    guidance: 'Elements with an input role (textbox, combobox, listbox, spinbutton, searchbox) must have accessible names so screen readers announce what data should be entered.',
    howToTest: 'Navigate to every ARIA input field with a screen reader and confirm a meaningful label is announced.',
    failExample: `<span role="textbox" tabindex="0"></span>`,
    passExample: `<label id="lbl">Search</label>
<span role="textbox" tabindex="0" aria-labelledby="lbl"></span>`,
    fixTip: 'Add aria-label or aria-labelledby to every element with an ARIA input role.',
  },

  'aria-meter-name': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'ARIA Meter Accessible Name',
    guidance: 'Elements with role="meter" represent a scalar measurement and must have an accessible name so screen reader users understand what is being measured.',
    howToTest: 'Navigate to meter elements with a screen reader and confirm a meaningful label (e.g. "Battery: 70%") is announced.',
    failExample: `<div role="meter" aria-valuenow="70" aria-valuemin="0" aria-valuemax="100">70%</div>`,
    passExample: `<div role="meter" aria-valuenow="70" aria-valuemin="0" aria-valuemax="100"
     aria-label="Battery level 70%">70%</div>`,
    fixTip: 'Add aria-label or aria-labelledby to describe what the meter measures.',
  },

  'aria-progressbar-name': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'ARIA Progressbar Accessible Name',
    guidance: 'Elements with role="progressbar" must have accessible names so screen reader users know what operation is in progress.',
    howToTest: 'Trigger the progress bar with a screen reader active and confirm a meaningful label is announced.',
    failExample: `<div role="progressbar" aria-valuenow="40" aria-valuemin="0" aria-valuemax="100"></div>`,
    passExample: `<div role="progressbar" aria-valuenow="40" aria-valuemin="0" aria-valuemax="100"
     aria-label="Uploading file: 40%"></div>`,
    fixTip: 'Add aria-label or aria-labelledby that describes the ongoing operation.',
  },

  'aria-prohibited-attr': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Prohibited Attribute',
    guidance: 'Certain ARIA attributes are explicitly prohibited on specific roles (e.g. aria-label on role="none"). Using them overrides native semantics or produces invalid markup.',
    howToTest: 'Check that no prohibited attributes are applied to elements with roles that forbid them.',
    failExample: `<!-- aria-label is prohibited on role="none" -->
<p role="none" aria-label="Description">Content</p>`,
    passExample: `<p>Content</p>`,
    fixTip: 'Remove prohibited attributes. If you need to label the element, give it a meaningful role that supports aria-label.',
  },

  'aria-required-attr': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Required Attributes',
    guidance: 'Some ARIA roles require specific attributes to function correctly (e.g. role="checkbox" requires aria-checked). Without the required attribute, the element\'s state is undefined for AT users.',
    howToTest: 'For every element with an ARIA role, verify all required ARIA attributes are present.',
    failExample: `<!-- aria-checked is required for role="checkbox" -->
<div role="checkbox">Accept terms</div>`,
    passExample: `<div role="checkbox" aria-checked="false">Accept terms</div>`,
    fixTip: 'Add all required ARIA attributes for the role. Refer to the WAI-ARIA spec for each role\'s required properties.',
  },

  'aria-required-children': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'ARIA Required Children',
    guidance: 'Container roles such as "list", "menu", and "tree" require specific child roles. Without the correct children, the structure is invalid and screen readers cannot convey the relationship between items.',
    howToTest: 'Inspect ARIA container elements and confirm their direct children have the required roles.',
    failExample: `<!-- role="list" requires children with role="listitem" -->
<div role="list">
  <div>Plain div child</div>
</div>`,
    passExample: `<div role="list">
  <div role="listitem">Item 1</div>
  <div role="listitem">Item 2</div>
</div>`,
    fixTip: 'Add the required child roles. Alternatively, use native HTML elements (<ul>/<ol> with <li>) which have the correct semantics automatically.',
  },

  'aria-required-parent': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'ARIA Required Parent',
    guidance: 'Some ARIA roles (e.g. "listitem", "option", "tab") must be contained within a specific parent role. Orphaned items lose their contextual meaning for screen reader users.',
    howToTest: 'Check that every element with a role requiring a parent is correctly nested within that parent.',
    failExample: `<!-- role="listitem" requires a parent with role="list" -->
<div role="listitem">Orphan item</div>`,
    passExample: `<div role="list">
  <div role="listitem">Item</div>
</div>`,
    fixTip: 'Wrap the element in the required parent role, or use native HTML (e.g. <li> inside <ul>) to achieve the same structure.',
  },

  'aria-roles': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Valid ARIA Role',
    guidance: 'Only valid WAI-ARIA roles may be used. An invalid role is ignored by assistive technology, leaving the element with no role semantics.',
    howToTest: 'Check every role attribute value against the WAI-ARIA specification\'s list of valid roles.',
    failExample: `<div role="superman">Content</div>`,
    passExample: `<div role="region" aria-label="Highlights">Content</div>`,
    fixTip: 'Replace the invalid role with a valid WAI-ARIA role, or remove the role attribute entirely to use the element\'s native semantics.',
  },

  'aria-text': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'ARIA Text Role on Focusable Element',
    guidance: 'role="text" groups inline text into a single accessible object for screen readers. Applying it to elements with focusable descendants causes those descendants to be unreachable when screen readers read the element as a single string.',
    howToTest: 'Find every element with role="text" and confirm it contains no focusable descendants.',
    failExample: `<span role="text"><a href="#">Visit our site</a></span>`,
    passExample: `<span role="text">Plain text content with no links</span>`,
    fixTip: 'Remove role="text" from any element that contains interactive or focusable children.',
  },

  'aria-toggle-field-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Toggle Field Accessible Name',
    guidance: 'Toggle controls with roles such as "checkbox", "radio", "switch" must have accessible names so screen reader users know what they are toggling.',
    howToTest: 'Navigate to every ARIA toggle control with a screen reader and confirm a meaningful label is announced along with the current state.',
    failExample: `<div role="switch" aria-checked="false"></div>`,
    passExample: `<div role="switch" aria-checked="false" aria-label="Enable dark mode">
  Dark mode
</div>`,
    fixTip: 'Provide visible text content, aria-label, or aria-labelledby on every ARIA toggle field.',
  },

  'aria-tooltip-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'ARIA Tooltip Accessible Name',
    guidance: 'Elements with role="tooltip" must contain text so that assistive technologies can convey the tooltip content to users.',
    howToTest: 'Trigger the tooltip with a screen reader active and confirm the tooltip text is announced.',
    failExample: `<div role="tooltip" id="tip"></div>`,
    passExample: `<div role="tooltip" id="tip">Required field — enter your full name</div>`,
    fixTip: 'Add descriptive text content inside the tooltip element.',
  },

  'aria-treeitem-name': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'ARIA Tree Item Accessible Name',
    guidance: 'Elements with role="treeitem" must have accessible names so screen reader users can distinguish between items in a tree widget.',
    howToTest: 'Navigate the tree widget with a screen reader and confirm each item is announced with a meaningful label.',
    failExample: `<div role="tree">
  <div role="treeitem"></div>
</div>`,
    passExample: `<div role="tree">
  <div role="treeitem" aria-label="Documents folder" aria-expanded="false">
    Documents
  </div>
</div>`,
    fixTip: 'Add visible text or aria-label to every element with role="treeitem".',
  },

  'aria-valid-attr': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Valid ARIA Attribute Name',
    guidance: 'Only attributes defined in the WAI-ARIA specification (starting with "aria-") may be used as ARIA attributes. Custom or misspelled aria-* attributes are silently ignored by assistive technology.',
    howToTest: 'Validate all aria-* attribute names against the WAI-ARIA specification.',
    failExample: `<div aria-lable="Name" aria-describedbye="hint">Field</div>`,
    passExample: `<div aria-label="Name" aria-describedby="hint">Field</div>`,
    fixTip: 'Correct the spelling of aria-* attributes. Use the official attribute list from the WAI-ARIA spec.',
  },

  'aria-valid-attr-value': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Valid ARIA Attribute Value',
    guidance: 'ARIA attributes must have values from the permitted set. An invalid value (e.g. aria-live="now") is not understood by assistive technology.',
    howToTest: 'Check every aria-* attribute value against the permitted values in the WAI-ARIA specification.',
    failExample: `<div aria-live="now">Status</div>`,
    passExample: `<div aria-live="polite">Status</div>`,
    fixTip: 'Replace invalid values with the correct tokens from the WAI-ARIA specification (e.g. aria-live must be "off", "polite", or "assertive").',
  },

  'autocomplete-valid': {
    successCriteriaId: '1.3.5',
    wcagLevel: 'AA',
    title: 'Valid Autocomplete Attribute',
    guidance: 'The autocomplete attribute must use valid tokens from the HTML specification so that browsers and assistive technology can auto-populate form fields on behalf of users with cognitive disabilities.',
    howToTest: 'Check every autocomplete attribute value against the WHATWG list of valid autofill detail tokens.',
    failExample: `<label for="n">Name</label>
<input id="n" type="text" autocomplete="fullname">`,
    passExample: `<label for="n">Name</label>
<input id="n" type="text" autocomplete="name">`,
    fixTip: 'Replace invalid tokens with valid ones from the HTML spec (e.g. "name", "email", "street-address", "new-password").',
  },

  'avoid-inline-spacing': {
    successCriteriaId: '1.4.12',
    wcagLevel: 'AA',
    title: 'No !important on Text Spacing',
    guidance: 'WCAG 1.4.12 requires that text remains readable when users apply custom spacing via a user stylesheet or browser extension. Using !important on letter-spacing, word-spacing, line-height, or padding overrides those user customisations.',
    howToTest: 'Apply the bookmarklet from the WCAG 1.4.12 technique and verify no text becomes unreadable or overlaps.',
    failExample: `<p style="letter-spacing: 0 !important; line-height: 1 !important;">
  Text with locked spacing
</p>`,
    passExample: `<p>Text with normal spacing</p>`,
    fixTip: 'Remove !important from letter-spacing, word-spacing, line-height, and padding properties in both inline styles and CSS.',
  },

  'blink': {
    successCriteriaId: '2.2.2',
    wcagLevel: 'A',
    title: 'No Blinking Content',
    guidance: 'The <blink> element causes text to flash on and off indefinitely, which can trigger seizures in people with photosensitive epilepsy and is distracting for users with attention disorders. It has no mechanism to pause or stop.',
    howToTest: 'Search for <blink> tags in the HTML source.',
    failExample: `<blink>Important notice!</blink>`,
    passExample: `<p>Important notice!</p>`,
    fixTip: 'Remove <blink> entirely. If emphasis is needed use CSS, bold, or colour with sufficient contrast.',
  },

  'button-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Button Accessible Name',
    guidance: 'Every <button> and element with role="button" must have an accessible name. Without a name, screen readers announce only "button" with no indication of what it does.',
    howToTest: 'Navigate to every button with a screen reader and confirm a meaningful action name is announced.',
    failExample: `<button><img src="icon.png"></button>`,
    passExample: `<!-- Option 1: visible text -->
<button>Save document</button>

<!-- Option 2: aria-label for icon-only buttons -->
<button aria-label="Save document"><img src="icon.png" alt=""></button>`,
    fixTip: 'Add visible text inside the button, or add aria-label / aria-labelledby for icon-only buttons. Set alt="" on purely decorative icons inside buttons.',
  },

  'bypass': {
    successCriteriaId: '2.4.1',
    wcagLevel: 'A',
    title: 'Bypass Blocks (Skip Link)',
    guidance: 'Pages with repeated navigation blocks must provide a mechanism (usually a skip link) so keyboard-only users can jump directly to the main content without tabbing through the navigation on every page load.',
    howToTest: 'Press Tab on page load. The first focusable element should be a "Skip to main content" link. Activate it and confirm focus moves to the main content area.',
    failExample: `<body>
  <nav><a href="/">Home</a><a href="/about">About</a></nav>
  <main><p>Content</p></main>
</body>`,
    passExample: `<body>
  <a href="#main" class="skip-link">Skip to main content</a>
  <nav><a href="/">Home</a><a href="/about">About</a></nav>
  <main id="main"><p>Content</p></main>
</body>`,
    fixTip: 'Add a visually-hidden skip link as the first focusable element. Ensure the target ID exists and the target element is focusable (add tabindex="-1" if needed).',
  },

  'color-contrast': {
    successCriteriaId: '1.4.3',
    wcagLevel: 'AA',
    title: 'Colour Contrast (Minimum)',
    guidance: 'Text must have a contrast ratio of at least 4.5:1 against its background (3:1 for large text ≥ 18pt or 14pt bold). Low contrast is one of the most common barriers for users with low vision.',
    howToTest: 'Use a colour contrast checker (e.g. WebAIM Contrast Checker) for all text/background combinations. Check both normal and hover/focus states.',
    failExample: `<!-- #aaa on #fff = 2.32:1 — fails 4.5:1 requirement -->
<p style="color: #aaaaaa; background-color: #ffffff;">Low contrast text</p>`,
    passExample: `<!-- #595959 on #fff ≈ 7.0:1 — passes both AA and AAA -->
<p style="color: #595959; background-color: #ffffff;">Sufficient contrast text</p>`,
    fixTip: 'Darken the text colour or lighten/darken the background until the ratio meets 4.5:1. Use the WebAIM Contrast Checker or browser DevTools colour picker.',
  },

  'definition-list': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Valid Definition List Structure',
    guidance: 'The <dl> element must only contain <dt>, <dd>, or <div> as direct children. Any other element breaks the semantic structure that screen readers use to announce term–definition pairs.',
    howToTest: 'Inspect every <dl> element and confirm its direct children are only <dt>, <dd>, or wrapping <div> elements.',
    failExample: `<dl>
  <li>Invalid child</li>
  <p>Also invalid</p>
</dl>`,
    passExample: `<dl>
  <dt>Accessibility</dt>
  <dd>The practice of making websites usable by everyone.</dd>
</dl>`,
    fixTip: 'Replace invalid children with <dt> (terms) and <dd> (definitions). Group term–definition pairs in <div> wrappers if styling requires it.',
  },

  'dlitem': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Definition List Item Parent',
    guidance: '<dt> and <dd> elements must be direct children of a <dl> (or a <div> inside a <dl>). Orphaned list items lose their semantic meaning and are announced as plain text.',
    howToTest: 'Inspect every <dt> and <dd> and confirm each is inside a <dl>.',
    failExample: `<div>
  <dt>Term</dt>
  <dd>Definition</dd>
</div>`,
    passExample: `<dl>
  <dt>Term</dt>
  <dd>Definition</dd>
</dl>`,
    fixTip: 'Wrap <dt> and <dd> elements in a <dl> element.',
  },

  'document-title': {
    successCriteriaId: '2.4.2',
    wcagLevel: 'A',
    title: 'Page Has Title',
    guidance: 'Every page must have a non-empty <title> element. The title is the first thing screen readers announce when a page loads and is displayed in browser tabs, bookmarks, and search results.',
    howToTest: 'Check the browser tab / page title. Confirm it is descriptive and unique across your site.',
    failExample: `<!DOCTYPE html>
<html lang="en"><head></head><body><p>No title</p></body></html>`,
    passExample: `<!DOCTYPE html>
<html lang="en">
  <head><title>Products — ACME Shop</title></head>
  <body>...</body>
</html>`,
    fixTip: 'Add a meaningful <title> to every page that describes the current page and the site (format: "Page — Site Name").',
  },

  'duplicate-id-aria': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Unique IDs for ARIA References',
    guidance: 'When the same ID is used on multiple elements and one of them is referenced by aria-labelledby, aria-describedby, or a similar ARIA attribute, assistive technology cannot determine which element to use, resulting in incorrect announcements.',
    howToTest: 'Validate the HTML. Confirm every ID referenced by an ARIA attribute is unique in the document.',
    failExample: `<div id="label">City</div>
<div id="label">Country</div>
<input aria-labelledby="label" type="text">`,
    passExample: `<div id="city-label">City</div>
<input aria-labelledby="city-label" type="text">`,
    fixTip: 'Ensure every ID used in ARIA references is unique within the document.',
  },

  'empty-heading': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Empty Headings',
    guidance: 'Heading elements must have visible or accessible text. Screen readers include headings in the document outline. An empty heading confuses users navigating by heading and produces a meaningless entry in the outline.',
    howToTest: 'Navigate through headings with a screen reader (H key in most screen readers) and confirm every heading has meaningful text.',
    failExample: `<h2></h2>
<h2><span aria-hidden="true">✦</span></h2>`,
    passExample: `<h2>Product Features</h2>`,
    fixTip: 'Add meaningful text to every heading. If a heading is purely decorative, remove the heading tag and use CSS or an ARIA live region instead.',
  },

  'empty-table-header': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Empty Table Headers',
    guidance: 'A <th> element with no text content does not describe its column or row, so screen reader users cannot understand the data in that table.',
    howToTest: 'Navigate the table with a screen reader and confirm every header cell announces a label.',
    failExample: `<table>
  <tr><th></th><th>Price</th></tr>
  <tr><td>Widget</td><td>$10</td></tr>
</table>`,
    passExample: `<table>
  <tr><th>Product</th><th>Price</th></tr>
  <tr><td>Widget</td><td>$10</td></tr>
</table>`,
    fixTip: 'Add descriptive text to every <th> element. If the header is intentionally invisible, use a visually hidden class (e.g. .sr-only) rather than leaving it empty.',
  },

  'focus-order-semantics': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Focus Order Semantics',
    guidance: 'When a non-interactive element (e.g. <span>, <div>, <p>) is made focusable via tabindex="0", it should also have an appropriate ARIA role so screen reader users understand what type of control they have focused.',
    howToTest: 'Tab to the element with a screen reader. Confirm the element\'s role is announced meaningfully.',
    failExample: `<span tabindex="0">Activate filter</span>`,
    passExample: `<span role="button" tabindex="0">Activate filter</span>`,
    fixTip: 'Either use a native interactive element (<button>) or add an appropriate ARIA role to the focusable element.',
  },

  'form-field-multiple-labels': {
    successCriteriaId: '3.3.2',
    wcagLevel: 'A',
    title: 'No Multiple Labels for One Field',
    guidance: 'A form field must not have multiple conflicting label sources (e.g. both a <label> element and an aria-label). Multiple labels cause screen readers to concatenate them, producing a confusing announcement.',
    howToTest: 'Inspect every form field for multiple labelling mechanisms. Only one source should be active.',
    failExample: `<label for="q">Search</label>
<input id="q" type="text" aria-label="Enter search terms">`,
    passExample: `<label for="q">Search</label>
<input id="q" type="text">`,
    fixTip: 'Use only one labelling method per form field. Prefer a visible <label> element over aria-label.',
  },

  'frame-focusable-content': {
    successCriteriaId: '2.1.1',
    wcagLevel: 'A',
    title: 'Focusable Content Inside tabindex=-1 iframe',
    guidance: 'When an <iframe> has tabindex="-1" it is removed from the tab order. However if it contains focusable elements those elements may still receive focus through other mechanisms, leading to confusing behaviour.',
    howToTest: 'Check every <iframe tabindex="-1"> and confirm it does not contain focusable elements, or that the content is intentionally inert.',
    failExample: `<iframe tabindex="-1" src="page-with-button.html" title="Ad"></iframe>`,
    passExample: `<!-- Option 1: Remove tabindex="-1" if the iframe is interactive -->
<iframe src="page-with-button.html" title="Newsletter signup"></iframe>

<!-- Option 2: Keep tabindex="-1" only for purely decorative / non-interactive iframes -->
<iframe tabindex="-1" src="tracker.html" title="Analytics pixel" aria-hidden="true"></iframe>`,
    fixTip: 'Only use tabindex="-1" on iframes that contain no interactive content. If the iframe has interactive content, remove tabindex="-1".',
  },

  'frame-tested': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'iframe Testable by axe',
    guidance: 'axe-core cannot test cross-origin iframes or iframes with restricted policies. The content within those iframes must be manually tested for accessibility.',
    howToTest: 'Open the URL loaded by each untested iframe in a new tab and run an accessibility audit on it directly.',
    failExample: `<!-- Cross-origin iframe cannot be tested -->
<iframe src="https://external-site.com/widget" title="External widget"></iframe>`,
    passExample: `<!-- Same-origin iframe can be tested automatically -->
<iframe src="/internal/widget.html" title="Internal widget"></iframe>`,
    fixTip: 'Test iframe content separately. Where possible, host iframe content on the same origin so automated tools can reach it.',
  },

  'frame-title': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'iframe Has Title',
    guidance: 'Every <iframe> must have a descriptive title attribute. Screen reader users rely on the title to understand the purpose of an iframe before deciding whether to enter it.',
    howToTest: 'Inspect every <iframe> element. Confirm each has a non-empty, descriptive title.',
    failExample: `<iframe src="chart.html"></iframe>`,
    passExample: `<iframe src="chart.html" title="Q1 2024 Sales Bar Chart"></iframe>`,
    fixTip: 'Add a concise, descriptive title attribute to every <iframe>. If the iframe is decorative add title="Decorative" and aria-hidden="true".',
  },

  'frame-title-unique': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Unique iframe Titles',
    guidance: 'When multiple iframes share the same title, screen reader users cannot distinguish between them when navigating the frames list.',
    howToTest: 'List all iframe titles on the page and confirm each is unique.',
    failExample: `<iframe src="chart-a.html" title="Chart"></iframe>
<iframe src="chart-b.html" title="Chart"></iframe>`,
    passExample: `<iframe src="chart-a.html" title="Monthly Revenue Chart"></iframe>
<iframe src="chart-b.html" title="Monthly Expenses Chart"></iframe>`,
    fixTip: 'Give each iframe a unique, descriptive title that reflects its specific content.',
  },

  'heading-order': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Heading Level Order',
    guidance: 'Heading levels must not be skipped (e.g. jumping from <h1> to <h3> without an <h2>). Screen reader users navigate by headings and expect a logical, hierarchical document outline.',
    howToTest: 'List all headings on the page (e.g. using the HeadingsMap browser extension). Confirm levels descend by exactly 1 at a time.',
    failExample: `<h1>Page Title</h1>
<h3>Subsection</h3>`,
    passExample: `<h1>Page Title</h1>
<h2>Section</h2>
<h3>Subsection</h3>`,
    fixTip: 'Use heading levels in sequential order. A heading\'s level should reflect its position in the document hierarchy, not its visual size.',
  },

  'hidden-content': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Hidden Content Review',
    guidance: 'Content hidden with CSS (display:none, visibility:hidden) or the hidden attribute is inaccessible to all users. If that content serves a functional purpose (e.g. modal), it should be accessible when visible.',
    howToTest: 'Toggle all hidden content visible and verify it is semantically correct and accessible.',
    failExample: `<!-- Content hidden via CSS — cannot be tested automatically -->
<div style="display:none">
  <button>Important action</button>
</div>`,
    passExample: `<!-- When made visible, content should be fully accessible -->
<div id="modal" role="dialog" aria-labelledby="modal-title" aria-modal="true">
  <h2 id="modal-title">Confirm</h2>
  <button>OK</button>
</div>`,
    fixTip: 'Review all hidden content. Ensure modal dialogs trap focus and are announced correctly when shown. Use aria-hidden="true" on decorative content.',
  },

  'html-has-lang': {
    successCriteriaId: '3.1.1',
    wcagLevel: 'A',
    title: 'HTML lang Attribute',
    guidance: 'The <html> element must have a lang attribute. Screen readers use this to select the correct language voice and pronunciation rules.',
    howToTest: 'Inspect the opening <html> tag. Confirm it has a lang attribute with a valid language code.',
    failExample: `<html>
  <head><title>Page</title></head>
  <body>Content</body>
</html>`,
    passExample: `<html lang="en">
  <head><title>Page</title></head>
  <body>Content</body>
</html>`,
    fixTip: 'Add lang="xx" to the <html> element, where "xx" is the primary language BCP-47 code (e.g. "en", "fr", "de", "ar").',
  },

  'html-lang-valid': {
    successCriteriaId: '3.1.1',
    wcagLevel: 'A',
    title: 'HTML lang Value Valid',
    guidance: 'The lang attribute on the <html> element must be a valid BCP-47 language tag. An invalid code causes screen readers to use the wrong language engine.',
    howToTest: 'Validate the lang value at validator.w3.org or check against the IANA Language Subtag Registry.',
    failExample: `<html lang="english">`,
    passExample: `<html lang="en">`,
    fixTip: 'Use a valid BCP-47 language subtag (e.g. "en", "en-US", "fr", "zh-Hant").',
  },

  'html-xml-lang-mismatch': {
    successCriteriaId: '3.1.1',
    wcagLevel: 'A',
    title: 'HTML lang and xml:lang Match',
    guidance: 'When both lang and xml:lang are specified on <html>, they must agree on the primary language. A mismatch causes different AT to use different language settings.',
    howToTest: 'Check that the primary language subtag of lang and xml:lang are identical.',
    failExample: `<html lang="en" xml:lang="fr">`,
    passExample: `<html lang="en" xml:lang="en-US">`,
    fixTip: 'Ensure the base language of both lang and xml:lang attributes match (e.g. both start with "en").',
  },

  'image-alt': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'Image Alternative Text',
    guidance: 'Every <img> must have an alt attribute. If the image conveys information, the alt text should describe that information. If the image is purely decorative, use alt="" so screen readers skip it.',
    howToTest: 'For every image, verify: informative images have descriptive alt text; decorative images have alt=""; functional images (links/buttons) describe the destination/action.',
    failExample: `<img src="product.jpg">`,
    passExample: `<!-- Informative -->
<img src="product.jpg" alt="Blue wireless headphones with over-ear cushions">

<!-- Decorative -->
<img src="divider.png" alt="">

<!-- Functional (inside a link) -->
<a href="/cart"><img src="cart.png" alt="Shopping cart"></a>`,
    fixTip: 'Add meaningful alt text to informative images. Set alt="" on decorative images. For complex images (charts, diagrams) provide a longer text description nearby.',
  },

  'image-redundant-alt': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Non-Redundant Image Alt Text',
    guidance: 'If an image\'s alt text is identical to adjacent visible text (especially when wrapped in a link), screen readers announce the text twice, which is verbose and confusing.',
    howToTest: 'Check every linked image. If the link text and alt text are identical, the alt is redundant.',
    failExample: `<a href="/home">
  <img src="logo.png" alt="ACME Logo"> ACME Logo
</a>`,
    passExample: `<a href="/home">
  <img src="logo.png" alt=""> ACME Logo
</a>`,
    fixTip: 'When an image is accompanied by visible text that serves the same purpose, set alt="" on the image to avoid duplication.',
  },

  'input-button-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Input Button Accessible Name',
    guidance: '<input type="button">, type="submit", and type="reset" derive their accessible name from the value attribute. An empty or absent value leaves the button nameless.',
    howToTest: 'Tab to every input button with a screen reader and confirm a meaningful label is announced.',
    failExample: `<input type="submit" value="">
<input type="button" value="">`,
    passExample: `<input type="submit" value="Place Order">
<input type="button" value="Cancel">`,
    fixTip: 'Set a descriptive, non-empty value attribute on every input button.',
  },

  'input-image-alt': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'Input Image Alternative Text',
    guidance: '<input type="image"> acts as a submit button and must have alt text that describes the button\'s action, not the image\'s appearance.',
    howToTest: 'Activate the input[type=image] with a screen reader and confirm the announced text describes the action.',
    failExample: `<input type="image" src="submit-arrow.png">`,
    passExample: `<input type="image" src="submit-arrow.png" alt="Submit order">`,
    fixTip: 'Add an alt attribute describing the button\'s action, not the image itself (e.g. alt="Submit" not alt="Right arrow").',
  },

  'label': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Form Input Has Label',
    guidance: 'Every form input (<input>, <textarea>, <select>) must have a programmatically associated label. Without a label, screen reader users do not know what data to enter.',
    howToTest: 'Click on each form label and confirm focus moves to the associated input. Navigate with a screen reader and confirm every input announces a label.',
    failExample: `<input type="text" placeholder="Enter your name">`,
    passExample: `<!-- Option 1: <label for> -->
<label for="name">Full name</label>
<input id="name" type="text">

<!-- Option 2: wrapping label -->
<label>Full name <input type="text"></label>`,
    fixTip: 'Use a visible <label> element associated via for/id. Avoid using placeholder as the only label — placeholders disappear on input and have poor contrast.',
  },

  'label-content-name-mismatch': {
    successCriteriaId: '2.5.3',
    wcagLevel: 'A',
    title: 'Label and Accessible Name Match',
    guidance: 'The accessible name of an interactive control must contain the visible label text. When they differ, speech recognition users who speak the visible label cannot activate the control.',
    howToTest: 'Compare every control\'s visible text against its accessible name (computed via browser accessibility tree). The accessible name must contain the visible text.',
    failExample: `<!-- Visible: "Submit" — Accessible name: "Go away" — mismatch -->
<button aria-label="Go away">Submit</button>`,
    passExample: `<!-- Visible: "Submit" — Accessible name includes "Submit" -->
<button aria-label="Submit order form">Submit</button>

<!-- Or simply use visible text as the accessible name -->
<button>Submit</button>`,
    fixTip: 'Ensure aria-label / aria-labelledby contains the visible button text as a substring.',
  },

  'label-title-only': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Label Not Title-Only',
    guidance: 'Labelling a form field via the title attribute only is insufficient — the title is shown as a tooltip on hover and is not accessible on touch devices or reliably announced by all screen readers.',
    howToTest: 'Test form fields on a touch device or with a screen reader that does not read title attributes. Confirm all fields have visible, programmatic labels.',
    failExample: `<input type="text" title="Search the site">`,
    passExample: `<label for="search">Search</label>
<input id="search" type="text">`,
    fixTip: 'Replace title-only labels with a visible <label> element. The title attribute can be retained as supplementary information.',
  },

  'landmark-banner-is-top-level': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Banner Landmark at Top Level',
    guidance: 'The banner landmark (<header> or role="banner") must be a top-level landmark, not nested inside another landmark. Nesting it changes its meaning and breaks expected page structure.',
    howToTest: 'Inspect the landmark structure with a screen reader or browser accessibility tree. Confirm the banner is a direct descendant of <body>.',
    failExample: `<div role="navigation">
  <div role="banner">Site Header</div>
</div>`,
    passExample: `<header>Site Header</header>
<nav>Navigation</nav>`,
    fixTip: 'Move the <header> or role="banner" element to the top level, directly inside <body>.',
  },

  'landmark-complementary-is-top-level': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Complementary Landmark at Top Level',
    guidance: 'The complementary landmark (<aside> or role="complementary") should be a top-level landmark. Nesting it inside <main> implies it is part of the main content, which contradicts its "complementary" purpose.',
    howToTest: 'Confirm <aside> elements are siblings of <main>, not children.',
    failExample: `<main>
  <article>Main article</article>
  <aside>Related links</aside>
</main>`,
    passExample: `<main>
  <article>Main article</article>
</main>
<aside>Related links</aside>`,
    fixTip: 'Move <aside> elements to be siblings of <main> at the top level of the page.',
  },

  'landmark-contentinfo-is-top-level': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Contentinfo Landmark at Top Level',
    guidance: 'The contentinfo landmark (<footer> or role="contentinfo") must be a top-level landmark. Nesting it within another landmark changes its semantics.',
    howToTest: 'Verify the page footer (<footer>) is a direct child of <body> and not nested inside a section or other landmark.',
    failExample: `<div role="main">
  <div role="contentinfo">Footer content</div>
</div>`,
    passExample: `<main>Main content</main>
<footer>Footer content</footer>`,
    fixTip: 'Place the <footer> (or role="contentinfo" element) directly inside <body>, not inside another landmark.',
  },

  'landmark-main-is-top-level': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Main Landmark at Top Level',
    guidance: 'The <main> element (or role="main") must not be nested inside another landmark. It should be a direct child of <body> to correctly identify the primary content area of the page.',
    howToTest: 'Confirm <main> is a direct child of <body>.',
    failExample: `<div role="navigation">
  <main>Main content</main>
</div>`,
    passExample: `<nav>Navigation</nav>
<main>Main content</main>`,
    fixTip: 'Move the <main> element to be a direct child of <body>.',
  },

  'landmark-no-duplicate-banner': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Duplicate Banner Landmark',
    guidance: 'A page should have at most one top-level banner landmark. Multiple banners confuse the landmark navigation flow for screen reader users.',
    howToTest: 'Count top-level <header> elements and elements with role="banner". There should be at most one.',
    failExample: `<header>Main site header</header>
<header>Secondary header</header>`,
    passExample: `<header>Main site header</header>`,
    fixTip: 'Consolidate multiple banners into one. If a section needs a header, use a <div> or a contextual <header> inside an <article> or <section> (which does not create a banner landmark).',
  },

  'landmark-no-duplicate-contentinfo': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Duplicate Contentinfo Landmark',
    guidance: 'A page should have at most one top-level contentinfo landmark. Multiple footers at the top level create ambiguity for screen reader users navigating landmarks.',
    howToTest: 'Count top-level <footer> elements. There should be at most one.',
    failExample: `<footer>Main footer</footer>
<footer>Secondary footer</footer>`,
    passExample: `<footer>Site footer with copyright and links</footer>`,
    fixTip: 'Merge footer content into a single <footer> element. Contextual footers inside <article> or <section> do not create a contentinfo landmark and are allowed.',
  },

  'landmark-no-duplicate-main': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Duplicate Main Landmark',
    guidance: 'A page must have exactly one <main> landmark. Multiple <main> elements make it impossible for screen reader users to identify the primary content.',
    howToTest: 'Search for <main> elements and elements with role="main". There should be exactly one.',
    failExample: `<main>Content A</main>
<main>Content B</main>`,
    passExample: `<main>Primary page content</main>`,
    fixTip: 'Remove duplicate <main> elements and keep only one.',
  },

  'landmark-one-main': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Page Has One Main Landmark',
    guidance: 'Every page should have exactly one <main> landmark so screen reader users can jump directly to the primary content.',
    howToTest: 'Confirm the page contains one <main> element or one element with role="main".',
    failExample: `<body>
  <header>Header</header>
  <p>Content with no main landmark</p>
</body>`,
    passExample: `<body>
  <header>Header</header>
  <main>Primary content</main>
  <footer>Footer</footer>
</body>`,
    fixTip: 'Wrap the primary content in a <main> element.',
  },

  'landmark-unique': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Unique Landmark Labels',
    guidance: 'When multiple landmarks of the same type exist (e.g. two <nav> elements), each must have a unique accessible name via aria-label or aria-labelledby so users can distinguish between them in the landmarks list.',
    howToTest: 'Open the screen reader landmarks list and confirm every landmark of the same type has a distinct label.',
    failExample: `<nav aria-label="Navigation">...</nav>
<nav aria-label="Navigation">...</nav>`,
    passExample: `<nav aria-label="Main navigation">...</nav>
<nav aria-label="Footer navigation">...</nav>`,
    fixTip: 'Add unique aria-label values to differentiate landmarks of the same type.',
  },

  'link-in-text-block': {
    successCriteriaId: '1.4.1',
    wcagLevel: 'A',
    title: 'Link Distinguishable in Text',
    guidance: 'Links within blocks of text must be distinguishable from surrounding text by more than colour alone. Users who cannot perceive colour differences (colour blindness, low vision) must still be able to identify links.',
    howToTest: 'View the page in greyscale (browser dev tools or system setting). Confirm all inline links are still visually distinct from surrounding text.',
    failExample: `<p>Read our <a href="/policy" style="color:blue; text-decoration:none;">
  privacy policy
</a> for details.</p>`,
    passExample: `<p>Read our <a href="/policy">privacy policy</a> for details.</p>
<!-- Default browser underline provides non-colour distinction -->`,
    fixTip: 'Keep the default underline on inline links, or use a visual indicator other than colour alone (e.g. bold, border-bottom, background highlight).',
  },

  'link-name': {
    successCriteriaId: '2.4.4',
    wcagLevel: 'A',
    title: 'Link Has Accessible Name',
    guidance: 'Every <a> element must have an accessible name that describes its destination or purpose. An empty or icon-only link without alt/aria-label is announced as just "link" with no context.',
    howToTest: 'Navigate all links with a screen reader. Confirm each is announced with a meaningful name, not just "link" or "click here".',
    failExample: `<a href="/report"><img src="pdf-icon.png"></a>
<a href="#"></a>`,
    passExample: `<a href="/report"><img src="pdf-icon.png" alt="Download Q1 Report PDF"></a>
<a href="/report" aria-label="Download Q1 Report PDF"><img src="pdf-icon.png" alt=""></a>`,
    fixTip: 'Add descriptive text, alt text on a child image, or aria-label. Avoid generic labels like "click here" or "read more" — they are meaningless out of context.',
  },

  'list': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Valid List Structure',
    guidance: '<ul> and <ol> elements must only have <li> elements as direct children (other than <script> and <template>). Incorrect children break the semantic list that screen readers use to announce item counts.',
    howToTest: 'Inspect every <ul> and <ol> element and confirm each direct child is a <li>.',
    failExample: `<ul>
  <div>Item A</div>
  <p>Item B</p>
</ul>`,
    passExample: `<ul>
  <li>Item A</li>
  <li>Item B</li>
</ul>`,
    fixTip: 'Replace non-<li> direct children of lists with <li> elements. Use CSS for any styling needs.',
  },

  'listitem': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'List Item Has Parent List',
    guidance: '<li> elements must be contained within a <ul>, <ol>, or <menu> element. Orphaned <li> elements lose their list-item semantics and are announced unpredictably.',
    howToTest: 'Inspect every <li> element and confirm it is inside a <ul>, <ol>, or <menu>.',
    failExample: `<div>
  <li>Orphan item</li>
</div>`,
    passExample: `<ul>
  <li>Item</li>
</ul>`,
    fixTip: 'Wrap <li> elements in a parent <ul> or <ol>.',
  },

  'marquee': {
    successCriteriaId: '2.2.2',
    wcagLevel: 'A',
    title: 'No Marquee Element',
    guidance: 'The <marquee> element causes content to scroll continuously without a mechanism to pause or stop it. This fails WCAG 2.2.2 (Pause, Stop, Hide) and is distracting for users with attention or cognitive disabilities.',
    howToTest: 'Search the HTML source for <marquee> elements.',
    failExample: `<marquee>Breaking news: important announcement!</marquee>`,
    passExample: `<p>Breaking news: important announcement!</p>
<!-- If animation is needed use CSS with prefers-reduced-motion support -->`,
    fixTip: 'Remove <marquee> entirely. Use static text. If scrolling is a design requirement, implement it with CSS animations and include a pause button, and respect the prefers-reduced-motion media query.',
  },

  'meta-refresh': {
    successCriteriaId: '2.2.1',
    wcagLevel: 'A',
    title: 'No Auto-Refresh',
    guidance: 'Using <meta http-equiv="refresh"> with a time limit forces a page reload or redirect without user action. This disrupts screen reader reading, breaks back-button navigation, and can cause data loss in forms.',
    howToTest: 'Search the <head> for <meta http-equiv="refresh"> tags. If present, confirm the content value is 0 (instant redirect) or that an override mechanism exists.',
    failExample: `<meta http-equiv="refresh" content="30">`,
    passExample: `<!-- Remove the meta refresh entirely.
     For redirect pages, use a server-side 301 redirect instead. -->`,
    fixTip: 'Remove the meta refresh tag. Use server-side redirects for URL changes. If periodic content updates are needed, use ARIA live regions instead of page reloads.',
  },

  'meta-viewport': {
    successCriteriaId: '1.4.4',
    wcagLevel: 'AA',
    title: 'Viewport Does Not Disable Zoom',
    guidance: 'Setting user-scalable=no or maximum-scale=1 in the viewport meta tag prevents users from zooming the page. Many users with low vision rely on browser zoom to make content readable.',
    howToTest: 'Attempt to pinch-zoom or use Ctrl+/Cmd+ to zoom the page on a mobile device. Confirm zoom is not blocked.',
    failExample: `<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">`,
    passExample: `<meta name="viewport" content="width=device-width, initial-scale=1">`,
    fixTip: 'Remove user-scalable=no and ensure maximum-scale is at least 5 (or simply omit it). Design responsively so content reflows when zoomed.',
  },

  'meta-viewport-large': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Viewport Allows Large Scale Zoom',
    guidance: 'Limiting the maximum-scale to a small value (less than 5) prevents users from zooming sufficiently for readability.',
    howToTest: 'Check whether you can zoom to 500% without the page blocking it.',
    failExample: `<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=2">`,
    passExample: `<meta name="viewport" content="width=device-width, initial-scale=1">`,
    fixTip: 'Remove the maximum-scale restriction or set it to at least 5.',
  },

  'nested-interactive': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'No Nested Interactive Controls',
    guidance: 'Interactive controls (buttons, links, inputs) must not be nested inside other interactive controls. Nesting causes unpredictable focus behaviour and is not announced correctly by screen readers.',
    howToTest: 'Inspect the DOM. Confirm no <button>, <a>, <input>, or role="button/link" element is a descendant of another interactive element.',
    failExample: `<button>
  Save <a href="/help">Help</a>
</button>`,
    passExample: `<button>Save</button>
<a href="/help">Help</a>`,
    fixTip: 'Extract nested interactive elements and place them adjacently in the DOM.',
  },

  'no-autoplay-audio': {
    successCriteriaId: '1.4.2',
    wcagLevel: 'A',
    title: 'No Autoplay Audio',
    guidance: 'Audio that autoplays for more than 3 seconds without a mechanism to pause, stop, or mute it interferes with screen reader audio and is disorienting for users with auditory processing disorders.',
    howToTest: 'Load the page with audio turned on. Confirm no audio plays automatically, or that a visible pause/stop/mute control appears within 3 seconds.',
    failExample: `<audio autoplay loop>
  <source src="background.mp3" type="audio/mpeg">
</audio>`,
    passExample: `<!-- Option 1: Add controls, remove autoplay -->
<audio controls>
  <source src="background.mp3" type="audio/mpeg">
</audio>

<!-- Option 2: Autoplay only very short clips (<3 seconds) and do not loop -->`,
    fixTip: 'Remove the autoplay attribute, or provide a visible control to pause/stop/mute audio that autoplays. Use the muted attribute for ambient video that should autoplay silently.',
  },

  'object-alt': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'Object Has Text Alternative',
    guidance: '<object> elements embedding documents, Flash, or other content must have text alternatives. Screen readers cannot interpret binary content; they rely on the accessible name.',
    howToTest: 'Confirm every <object> has an aria-label, aria-labelledby, or inner text fallback that describes its content.',
    failExample: `<object data="report.pdf" type="application/pdf" width="600" height="400"></object>`,
    passExample: `<object data="report.pdf" type="application/pdf" width="600" height="400"
        aria-label="Q1 2024 Annual Report PDF">
  <p>Your browser does not support PDFs.
     <a href="report.pdf">Download the Q1 2024 Annual Report</a>.</p>
</object>`,
    fixTip: 'Add aria-label or aria-labelledby to the <object>, and include a text fallback inside the element for browsers that cannot render it.',
  },

  'p-as-heading': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Paragraph Not Used as Heading',
    guidance: 'Using a styled <p> element (bold, large font) as a visual heading does not create heading semantics. Screen reader users who navigate by heading will miss it entirely.',
    howToTest: 'Open the headings list in a screen reader. Confirm every visible section title is in that list.',
    failExample: `<p><strong>Section Overview</strong></p>
<p>Content follows...</p>`,
    passExample: `<h2>Section Overview</h2>
<p>Content follows...</p>`,
    fixTip: 'Replace styled paragraphs that act as headings with the appropriate <h1>–<h6> element. Adjust visual appearance with CSS, not markup.',
  },

  'page-has-heading-one': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Page Has h1',
    guidance: 'Every page should have at least one <h1> element that identifies the main topic. Screen reader users rely on the h1 as the starting point for understanding page content.',
    howToTest: 'Navigate to the page h1 (press 1 in most screen readers). Confirm it describes the page\'s main topic.',
    failExample: `<body>
  <h2>Contact Us</h2>
  <p>Fill in the form below.</p>
</body>`,
    passExample: `<body>
  <h1>Contact Us</h1>
  <h2>Send a message</h2>
</body>`,
    fixTip: 'Add an <h1> that summarises the page\'s main purpose. There should be exactly one <h1> per page.',
  },

  'presentation-role-conflict': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Presentation Role on Focusable Element',
    guidance: 'Elements with role="presentation" or role="none" are removed from the accessibility tree. If the element is tabbable (natural tab stop), this creates a confusing keyboard focus that announces nothing.',
    howToTest: 'Tab through the page and confirm no focusable element fails to announce its role and name.',
    failExample: `<!-- <a href> is naturally tabbable but role=presentation hides it -->
<a href="/about" role="presentation">About</a>`,
    passExample: `<a href="/about">About</a>`,
    fixTip: 'Do not apply role="presentation" or role="none" to focusable elements. Remove the role or make the element non-focusable (tabindex="-1") if it should be hidden from AT.',
  },

  'region': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Content Within Landmark',
    guidance: 'All significant page content should be contained within landmark regions (main, nav, header, footer, aside, or role="region"). Content outside landmarks cannot be found by screen reader users who navigate by landmarks.',
    howToTest: 'Open the landmarks list in a screen reader and confirm all meaningful content is accessible within at least one landmark.',
    failExample: `<body>
  <p>This important content is outside any landmark.</p>
  <footer>Footer</footer>
</body>`,
    passExample: `<body>
  <main>
    <p>Content is inside main landmark.</p>
  </main>
  <footer>Footer</footer>
</body>`,
    fixTip: 'Wrap all significant content in a landmark element. Use <main> for primary content, <nav> for navigation, <header>/<footer> for site header/footer.',
  },

  'role-img-alt': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'Role=img Has Accessible Name',
    guidance: 'Elements given role="img" (e.g. SVG or CSS-generated images) must have an accessible name so screen readers can convey the image\'s content.',
    howToTest: 'Navigate to every role="img" element with a screen reader and confirm a meaningful description is announced.',
    failExample: `<div role="img">
  <!-- SVG or CSS image with no label -->
</div>`,
    passExample: `<div role="img" aria-label="Pie chart showing 60% desktop and 40% mobile users">
  <!-- SVG or CSS image -->
</div>`,
    fixTip: 'Add aria-label or aria-labelledby to every element with role="img". For complex images, consider aria-describedby pointing to a longer description.',
  },

  'scope-attr-valid': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Valid Table Header Scope',
    guidance: 'The scope attribute on <th> must be "row", "col", "rowgroup", or "colgroup". An invalid value is ignored by assistive technology, breaking the programmatic association between headers and data cells.',
    howToTest: 'Inspect every scope attribute on <th> elements and confirm it is one of the four valid values.',
    failExample: `<table>
  <tr><th scope="cell">Header</th><td>Data</td></tr>
</table>`,
    passExample: `<table>
  <tr><th scope="col">Name</th><th scope="col">Age</th></tr>
  <tr><td>Alice</td><td>30</td></tr>
</table>`,
    fixTip: 'Use scope="col" for column headers and scope="row" for row headers. Use rowgroup/colgroup for grouped headers.',
  },

  'scrollable-region-focusable': {
    successCriteriaId: '2.1.1',
    wcagLevel: 'A',
    title: 'Scrollable Region Keyboard Accessible',
    guidance: 'Any region with scrollable overflow must be reachable via keyboard so users who cannot use a mouse can scroll through its content.',
    howToTest: 'Tab to the scrollable container. Confirm it receives focus and can be scrolled with arrow keys or Page Up/Down.',
    failExample: `<div style="overflow: auto; height: 200px;">
  <p>Long content that overflows...</p>
</div>`,
    passExample: `<div style="overflow: auto; height: 200px;" tabindex="0"
     role="region" aria-label="Product description">
  <p>Long content that overflows...</p>
</div>`,
    fixTip: 'Add tabindex="0" to scrollable containers that are not natively focusable. Add role="region" and aria-label to describe the scrollable area.',
  },

  'select-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Select Has Accessible Name',
    guidance: '<select> elements must have an associated label. Without one, screen reader users do not know what they are selecting.',
    howToTest: 'Navigate to every select element with a screen reader. Confirm a meaningful label is announced before the current value.',
    failExample: `<select>
  <option>Choose country</option>
  <option>Australia</option>
</select>`,
    passExample: `<label for="country">Country</label>
<select id="country">
  <option value="">Choose country</option>
  <option value="au">Australia</option>
</select>`,
    fixTip: 'Associate a visible <label> with each <select> using the for/id pair.',
  },

  'server-side-image-map': {
    successCriteriaId: '2.1.1',
    wcagLevel: 'A',
    title: 'No Server-Side Image Map',
    guidance: 'Server-side image maps (ismap attribute) send click coordinates to the server. Keyboard users cannot activate individual regions because coordinates are only generated by mouse clicks.',
    howToTest: 'Search for <img ismap> in the HTML. Confirm no server-side image maps are used for navigation.',
    failExample: `<a href="/map-handler">
  <img src="nav.png" ismap alt="Navigation map">
</a>`,
    passExample: `<!-- Use a client-side image map or standard navigation instead -->
<img src="nav.png" usemap="#navmap" alt="Navigation">
<map name="navmap">
  <area href="/home"    alt="Home"    shape="rect" coords="0,0,100,50">
  <area href="/about"   alt="About"   shape="rect" coords="100,0,200,50">
</map>`,
    fixTip: 'Replace server-side image maps with client-side image maps (<map> + <area>) or with standard HTML navigation (links, buttons).',
  },

  'skip-link': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Skip Link Has Valid Target',
    guidance: 'A skip link that points to a non-existent or non-focusable anchor does nothing when activated. The target element must exist and be focusable.',
    howToTest: 'Tab to the skip link and press Enter. Confirm focus moves to the main content area.',
    failExample: `<a href="#main-content">Skip to main content</a>
<!-- No element with id="main-content" exists -->
<nav>...</nav>`,
    passExample: `<a href="#main-content">Skip to main content</a>
<nav>...</nav>
<main id="main-content" tabindex="-1">
  <h1>Page Title</h1>
</main>`,
    fixTip: 'Ensure the skip link\'s href target ID exists in the DOM. If the target is not natively focusable, add tabindex="-1" so focus can be programmatically moved to it.',
  },

  'summary-name': {
    successCriteriaId: '4.1.2',
    wcagLevel: 'A',
    title: 'Summary Has Accessible Name',
    guidance: 'The <summary> element acts as a toggle button for a <details> disclosure. Without accessible text, screen reader users cannot understand what will be revealed.',
    howToTest: 'Tab to the <summary> element with a screen reader. Confirm a meaningful label is announced.',
    failExample: `<details>
  <summary></summary>
  Full product description here.
</details>`,
    passExample: `<details>
  <summary>Show full product description</summary>
  Full product description here.
</details>`,
    fixTip: 'Add descriptive text inside the <summary> element that explains what content will be disclosed.',
  },

  'svg-img-alt': {
    successCriteriaId: '1.1.1',
    wcagLevel: 'A',
    title: 'SVG Role=img Has Accessible Name',
    guidance: 'When an <svg> is given role="img" it is treated as an image by assistive technology and must have an accessible name. Without one, screen readers may announce it as "unlabelled image".',
    howToTest: 'Navigate to SVG images with a screen reader. Confirm each is announced with a meaningful label.',
    failExample: `<svg role="img" width="200" height="100">
  <rect width="200" height="100" fill="blue"/>
</svg>`,
    passExample: `<!-- Option 1: aria-label on the SVG -->
<svg role="img" aria-label="Blue rectangle representing the sky" width="200" height="100">
  <rect width="200" height="100" fill="blue"/>
</svg>

<!-- Option 2: <title> inside the SVG -->
<svg role="img" aria-labelledby="svg-title" width="200" height="100">
  <title id="svg-title">Blue rectangle representing the sky</title>
  <rect width="200" height="100" fill="blue"/>
</svg>`,
    fixTip: 'Add aria-label to the <svg> or include a <title> child element and reference it with aria-labelledby.',
  },

  'tabindex': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'No Positive tabindex',
    guidance: 'tabindex values greater than 0 explicitly set the tab order ahead of natural DOM order. This creates a confusing navigation sequence that diverges from the visual layout.',
    howToTest: 'Search the DOM for tabindex values > 0 and verify the tab order matches the visual reading order.',
    failExample: `<button tabindex="3">First visually but third in tab order</button>
<button tabindex="1">First in tab order</button>`,
    passExample: `<!-- Use tabindex="0" to add to natural tab order, or restructure the DOM -->
<button>Naturally ordered button</button>`,
    fixTip: 'Use tabindex="0" to include an element in the natural tab order, or tabindex="-1" to exclude it. Restructure the DOM to match the desired visual and reading order instead of using positive tabindex.',
  },

  'table-duplicate-name': {
    successCriteriaId: null,
    wcagLevel: 'best-practice',
    title: 'Table Caption and Summary Not Identical',
    guidance: 'When a table\'s <caption> and summary attribute contain the same text, screen readers announce the description twice. Each should provide distinct information.',
    howToTest: 'For tables with both a caption and summary, confirm the text is not identical.',
    failExample: `<table summary="Sales data">
  <caption>Sales data</caption>
  <tr><td>Q1</td><td>$10,000</td></tr>
</table>`,
    passExample: `<table summary="Rows represent quarters, columns represent regions">
  <caption>Quarterly Sales by Region</caption>
  <tr><td>Q1</td><td>$10,000</td></tr>
</table>`,
    fixTip: 'Use <caption> for a brief title and the summary attribute for a structural description of how to navigate the table.',
  },

  'table-fake-caption': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'No Fake Table Caption',
    guidance: 'Using a merged data cell (colspan spanning all columns) as a visual table title is not the same as a semantic <caption>. Screen readers do not identify it as a table title.',
    howToTest: 'Navigate to the table with a screen reader. Confirm the table is announced with a proper caption, not just the first data row.',
    failExample: `<table>
  <tr><td colspan="3"><strong>Monthly Sales Report</strong></td></tr>
  <tr><td>Jan</td><td>Feb</td><td>Mar</td></tr>
</table>`,
    passExample: `<table>
  <caption>Monthly Sales Report</caption>
  <tr><th scope="col">Jan</th><th scope="col">Feb</th><th scope="col">Mar</th></tr>
  <tr><td>$1k</td><td>$2k</td><td>$3k</td></tr>
</table>`,
    fixTip: 'Replace the spanning data cell title with a <caption> element as the first child of <table>.',
  },

  'td-has-header': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Data Cells Have Headers',
    guidance: 'Complex data tables (multiple rows and columns) must associate every data cell with at least one header cell so screen reader users can understand the context of each value.',
    howToTest: 'Navigate the table cell by cell with a screen reader. Confirm the relevant row and column headers are announced with each data cell.',
    failExample: `<table>
  <tr><td>Alice</td><td>Engineer</td><td>$90k</td></tr>
  <tr><td>Bob</td><td>Manager</td><td>$110k</td></tr>
</table>`,
    passExample: `<table>
  <tr>
    <th scope="col">Name</th>
    <th scope="col">Role</th>
    <th scope="col">Salary</th>
  </tr>
  <tr><td>Alice</td><td>Engineer</td><td>$90k</td></tr>
</table>`,
    fixTip: 'Add <th scope="col"> header cells for columns and/or <th scope="row"> for rows.',
  },

  'td-headers-attr': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'headers Attribute References Valid IDs',
    guidance: 'The headers attribute on a <td> must reference valid <th> IDs that exist in the same table. Invalid or missing references break the programmatic association between headers and data.',
    howToTest: 'Verify that every ID listed in a headers attribute corresponds to a <th> in the same table.',
    failExample: `<table>
  <tr><th id="h-name">Name</th></tr>
  <tr><td headers="h-name h-missing">Alice</td></tr>
</table>`,
    passExample: `<table>
  <tr><th id="h-name">Name</th><th id="h-role">Role</th></tr>
  <tr><td headers="h-name">Alice</td><td headers="h-role">Engineer</td></tr>
</table>`,
    fixTip: 'Audit every headers attribute and remove IDs that do not correspond to existing <th> elements in the same table.',
  },

  'th-has-data-cells': {
    successCriteriaId: '1.3.1',
    wcagLevel: 'A',
    title: 'Table Header Has Data Cells',
    guidance: 'Every <th> must be associated with at least one <td> data cell. A header with no corresponding data is misleading and suggests incomplete or incorrectly structured table markup.',
    howToTest: 'Navigate each <th> with a screen reader and confirm it correctly describes the data cells in its column or row.',
    failExample: `<table>
  <tr><th>Product</th><th>Price</th></tr>
  <!-- No data rows — headers have no data cells -->
</table>`,
    passExample: `<table>
  <tr><th scope="col">Product</th><th scope="col">Price</th></tr>
  <tr><td>Widget</td><td>$10</td></tr>
</table>`,
    fixTip: 'Add data rows with <td> cells that correspond to each <th>, or remove header cells that have no associated data.',
  },

  'valid-lang': {
    successCriteriaId: '3.1.2',
    wcagLevel: 'AA',
    title: 'Element lang Attribute Valid',
    guidance: 'When a lang attribute is applied to an inline element (to indicate a passage in a different language), its value must be a valid BCP-47 code. An invalid code causes screen readers to mispronounce the text.',
    howToTest: 'Inspect every lang attribute on child elements and validate each value.',
    failExample: `<p>The French word for hello is <span lang="frnch">bonjour</span>.</p>`,
    passExample: `<p>The French word for hello is <span lang="fr">bonjour</span>.</p>`,
    fixTip: 'Correct the lang attribute to a valid BCP-47 subtag (e.g. "fr", "de", "zh-Hant").',
  },

  'video-caption': {
    successCriteriaId: '1.2.2',
    wcagLevel: 'A',
    title: 'Video Has Captions',
    guidance: 'Pre-recorded video with audio must have synchronised captions. Captions are essential for deaf and hard-of-hearing users to access the audio content of a video.',
    howToTest: 'Play every video. Confirm a caption track (CC) is available and accurately reflects the spoken content and relevant sounds.',
    failExample: `<video controls width="640">
  <source src="presentation.mp4" type="video/mp4">
</video>`,
    passExample: `<video controls width="640">
  <source src="presentation.mp4" type="video/mp4">
  <track kind="captions" src="presentation-en.vtt" srclang="en" label="English" default>
</video>`,
    fixTip: 'Add a <track kind="captions"> element to every <video>. Use a WebVTT (.vtt) or SRT file with accurate, time-synchronised captions.',
  },

};

Object.freeze(rulesGuide);

module.exports = rulesGuide;
