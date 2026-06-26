# 1. About

Observarium is a client-server web application for amateur astronomers intended to
be used primarily from a mobile phone. It helps to:

- Identify interesting objects on the sky
- Find objects using a standard 8x50 finder scope
- Track observations
- Memorize useful information using quizzes

# 2. Basic Concepts

## 2.1 Space Object Data

IMPORTANT: Only objects observable from Europe are included.

a. Stars up to magnitude MAX_STAR_MAGNITUDE.

b. Objects of the Messier catalogue.

c. NON_MESSIER_NUM brightest non-Messier deep sky objects (skip
large nebulae that are difficult to observe visually).

d. Sun, Moon, planets and asteroids till magnitude ASTEROID_MAX_MAGNITUDE
with the ability to track their positions and apparent magnitude in the sky for
any date and time.

e. Constellations: the connectors between stars, boundaries and names.

f. Double-star information is attached directly to stars in the `stars.mMAG.json`
output. A pair is included only when both components are within the current
`--max-mag` limit and separation is within a configurable observable range
(`--min-double-star-sep` to 60 arcsec). For systems with more than two
components (AB, AC, BC...) store all available pair-wise records. Where WDS
notes indicate a physical pair, store this as `"phys": "AB"` (component id).

g. Basic schematic map of the Moon.

For each object (whenever relevant and known) we store:

1. Name
2. One catalogue number (Messier, NGC, Cadwell, for stars HD, SAO, HIP etc.)
3. Distance (including accuracy indication if available)
4. Type (spiral galaxy, elliptical galaxy, open cluster, globular cluster,
   planetary nebula, reflection nebula, emission nebula, dark nebula, variable
   star, double star)
5. Coordinates (RA/Dec) and containing constellation.
6. Apparent magnitude
7. Size (either radius or width x height)
8. Orientation (for non-circular objects)
9. Data specific for individual objects:
   9a. Apparent magnitude range for variable stars
   9b. Central star magnitude for planetary nebulae
   9c. Star classification using the Harvard spectral system
10. Images of the most interesting objects in resolution up to 400x400 and medium
    JPG quality (like 70%) to save space.
11. Short text information highlighting specifics of this object (like
    "extremely red star", "star with very fast motion", "brightest globular
    cluster in the sky" etc.)

## 2.2 User Interface

a. The app is intended to be used primarily during nightly observations, so the
UI must not break eye accommodation to the darkness. But sometimes the app is
used also in daily light. Therefore the app supports two color schemes:

- Daily (colourful)
- Nightly - only black, red and blue allowed (NO green). For content it uses
  mostly red as it has better readability than blue in low screen brightness.

b. The app takes the time and geographical location into account. Location is
obtained automatically via the browser's geolocation API (GPS). The app does
not work with compass and gyroscope data; device orientation is ignored.

c. The application always starts in a full screen mode and disables zooming and
scrolling (allowed only in some screens, e. g. "Object Details").

d. Because of the nightly mode the app implements its own on-screen keyboard. It
supports two layouts - Czech and English.

The keyboard is implemented using on-screen buttons and a custom text renderer
(a styled `<div>`) rather than a real `<input>` or `<textarea>`. Form values are
passed via `<input type="hidden">` elements. Since no focusable input is visible,
Android Chrome does not trigger the system keyboard. Known limitations:

- The cursor can only be moved using on-screen arrow buttons, not by tapping into text.
- Clipboard paste is not supported.
- Native autocorrect and autocomplete are disabled (intentional for astronomical names).
- Multi-line inputs (observation notes) scroll vertically within a fixed-height area.
  Any UI component that renders a real `<input>` internally (e.g. date pickers) must
  follow the same pattern to prevent the system keyboard from flashing on focus.

e. For any delete operation there must be a confirmation dialog.

f. Whenever the app is about to contact the server (object data or observation data
synchronization) and the app does not have a valid token, the user is asked to
enter their username and password.

g. Before starting of any quiz the user is asked to select between global/local
quiz (local quiz works only with objects near the center of current view in the
Main screen) and quiz difficulty (easy/medium/hard) - the higher
difficulty the less bright objects are included in the quiz. There is no
score of a quiz — instead the quiz runs until the user has answered every
question in the quiz correctly at least once. After each incorrect answer in the quiz the
correct answer is shown. A "Back" button is always available to exit the quiz at any time.

A progress indicator is displayed throughout the quiz. It reflects how close
the user is to completing the quiz: a correct answer increases it, an incorrect
answer decreases it (it cannot drop below zero). The indicator is calculated as
a weighted ratio of mastered questions to the total question pool.

Quiz state is saved to local storage. If the user exits and later starts a quiz
of the same type and difficulty, they are presented with the usual global/local
selection screen plus an additional option: "Continue previous quiz". If the user
does not choose to continue, the saved state is discarded and a new quiz begins.

## 2.3 Storage

Both object data and observation data are stored in the browser IndexedDB.
The Cognito access token (obtained at login) is stored in sessionStorage and
used for all subsequent API calls within the session.

# 3. Architecture

## 3.1 Solution Components

### 3.1.1 Client

A lightweight Svelte (with Vite) application with JavaScript (no
TypeScript) built as a single page app. Object data are not part of the
app built - this data should be fetched from the server and stored in
the browser IndexedDB (including object images).

### 3.1.2 Server

The server part is a Python Lambda function (for AWS) with an option to run it
locally using a lightweight wrapper (not something like AWS SAM). The Lambda
authenticates users against Cognito (returning the Cognito access token to the
client), verifies the Cognito JWT on all subsequent calls using Cognito's JWKS
endpoint, and returns pre-signed S3 URLs for large data fetches (object data,
images). Observation data is read/written directly by the Lambda. The Lambda
Function URL has CORS configured to allow requests from the client origin.

### 3.1.3 Data Preparation App

This app downloads space data (star catalogues, double star catalogues, images
etc.) from internet sources, filters it out (visible from Europe,
magnitude restrictions etc.) and converts it to a compact single
JSON and properly sized images. There is a command line interface supporting
various options to sync only part of the data (e. g. only stars, filter a
specific object for a test run). The app must incrementally update the data
already downloaded. Data is stored locally in uncompressed form to support
incremental updates.

`make deploy` detects which local data files have changed since the last
deployment, compresses them into the appropriate ZIP files, and uploads them
to S3. This covers both the object data ZIP (DEFLATE) and the image ZIP (STORE).

### 3.1.4 OpenTofu Deployment

We use OpenTofu (Terraform-compatible) with a local state file to deploy to
AWS. A make task
`make deploy` should be supported from the root with `AWS_PROFILE=personal`.
It performs the following in order:

1. Runs `tofu init -upgrade` and applies infrastructure changes.
2. Deploys updated Lambda code.
3. Detects changed data files, re-zips them, and uploads to S3.
4. Deploys the built Svelte client to S3 and serves it through CloudFront.

At the end of deployment, the Makefile prints both endpoints:

- Client URL (CloudFront default domain)
- Server URL (Lambda Function URL)

No CI/CD in scope.

## 3.2 AWS Cloud Components

The cloud deployment is intended to be lightweight and cheap. It counts with this
components:

### 3.2.1 Lambda

A Lambda exposed via a Lambda Function URL (no API Gateway). CORS is configured
on the Function URL to allow requests from local development origins and the
CloudFront client origin.
The Lambda covers the following operations:

- user login: calls Cognito `InitiateAuth` with the supplied username and password
  and returns the Cognito access token to the client
- read objects: verifies the Cognito JWT, returns a short-lived pre-signed S3 URL
  for the object data ZIP
- read images: verifies the Cognito JWT, returns a short-lived pre-signed S3 URL
  for the image ZIP
- read user observations: verifies the Cognito JWT, reads and returns the user's
  observation JSON from S3
- add/modify/delete observations: verifies the Cognito JWT, updates the user's
  observation JSON in S3

### 3.2.2 S3

Two S3 buckets:

**Data bucket** (private, accessed only via Lambda pre-signed URLs):

- Object data ZIP (JSON compressed with DEFLATE, produced by `make deploy`)
- Image ZIP (JPEG files bundled with STORE method, produced by `make deploy`)
- User observation data (one JSON file per user)

**Client bucket** (S3 origin for frontend assets):

- Built Svelte SPA (HTML, JS, CSS assets)

### 3.2.3 CloudFront

CloudFront serves the client app over HTTPS using the default CloudFront domain
(`*.cloudfront.net`). It fronts the client S3 bucket, uses a short cache TTL,
and provides SPA fallback to `index.html` for unknown routes.

### 3.2.4 AWS Cognito

Used for user management. The client app can still be used without authentication.
Authentication is only needed for syncing data (reading object data,
reading/writing user observations). AWS Cognito is used only as an auth backend —
the user fills in their username and password in the application, the Lambda calls
Cognito's `InitiateAuth` API, and the returned Cognito access token is passed back
to the client and stored in sessionStorage for the duration of the session.

### 3.2.5 IAM Role

IAM role for the lambda function.

### 3.2.6 CloudWatch

A named log group for the lambda function.

# 4. Common UI Elements

## 4.1 Top Bar

The top bar is present on all screens and contains:

- Date and time (editable — tapping opens a custom date-time picker styled for
  the current color scheme, allowing the sky to be viewed at a different time).
- FOV (only on the Main Screen or Finder View)
- In case some object is selected, display:
  - Icon representing object type
  - Object name or catalogue number
  - Name of the constellation the object belongs to
    If we click this the box with this information, we are sent to the "Object Details"
    screen.
- Menu toggle button
- Battery status (if known)

The Menu toggle button should be in the middle.

## 4.2 Menu

The menu has the following items (each one represented by a suitable SVG icon):

- Toggle color scheme (daily/nightly)
- Toggle constellation lines
- Toggle constellation boundaries
- Toggle deep sky objects
- Toggle horizon boundary
- Toggle normal view / finder view
- Toggle FOV circle (on by default; shows the finder FOV footprint on the Main Screen)
- Search
- Observations
- Telescopes
- Finder scope quiz
- Constellation quiz
- Deep sky quiz
- Find planet quiz
- Moon quiz
- Update object data
- Synchronize observation data (when unsynchronized changes exist, shows the count as a badge)
- About

# 5. Screens

## 5.1 Welcome Screen

The Welcome screen is shown when the IndexedDB is not found. It contains:

- Welcome message
- Application name including app version date
- Information about application
- A username and password input
- A button "Load Application Data".

After filling in the credentials and pressing the button the app loads the data
in the following order:

a. Object data
b. Images
c. User data

Each part is reported with a progress bar along with a message about what is
currently loading and the size of the data transferred.

## 5.2 Main Screen

The main screen displays a rendered sky fragment in Zenith corresponding to
DEFAULT_FOV (30 degrees by default) and current date and time. In the default
setup the following elements are rendered:

- Stars and planets up to magnitude NORMAL_VIEW_MAX_STAR_MAGNITUDE (5 by default)
- Deep sky objects up to magnitude NORMAL_VIEW_MAX_DSO_MAGNITUDE (8 by default)
- Boundary of the horizon (corresponding to location and time)

Notes:

- Point size has to reflect the apparent magnitude.
- Variable stars with magnitude range higher than 2 has to be marked graphically.

By default no labels, no constellation lines and boundaries.

The following input operations are supported:

- Moving the view by swiping
- Zooming by two fingers gesture. The zoom range is
  limited by NORMAL_VIEW_MIN_FOV (2 degrees by default) and NORMAL_VIEW_MAX_FOV
  (60 degrees by default).
- Tapping on an object to select or deselect it. If exactly one object is
  within the tap radius, it is toggled: already selected → deselected,
  otherwise → selected. If multiple nearby objects are ambiguous, a loupe
  overlay appears showing a magnified square view centred on the tap area; the
  user taps once inside the loupe to pick the intended object (closest to the
  tap point is selected), or dismisses it with the close button. Tapping empty
  sky always deselects.
- Tapping the selected object's name in the top bar (row 2) opens the Object
  Details (About) panel. Closing About with the back button or Escape returns
  to the sky view with the object still selected.
- When the FOV circle toggle is on (see Menu), a dashed circle is drawn on the Main
  Screen representing the footprint of the Finder FOV (FINDER_FOV degrees). This helps
  the user build spatial intuition between the two views.

The limiting magnitudes are changed intelligently
according to the FOV. Neither the swipe nor the zoom should allow the user
to get to the area (not even partially) for which we don't have data (as
it is not visible from Europe).

## 5.3 Finder View

The finder view is displayed in a round view and FOV FINDER_FOV degrees (7.5 by
default, corresponding to an 8x50 finder scope). In the finder view we
can only swipe, zoom is not allowed. Constellation lines and boundaries are not
shown irrespective of setup.

Below (or next to in a landscape mode) the finder view there are the following buttons:

- Switch to normal view (Main screen)
- Search object
- Guide to find the object
- Record guide to find object

### 5.3.1 Guide to Find the Object

The button is only rendered if we have previously searched for an object
for which at least one finding path is defined. If we click the button and
more finding paths are defined the user is first asked to select from
the possible starting points (with an additional option "Cancel"). After the
user selects the start point (or it is clear as there is just one finding
path) the scope view is moved to the start point and the vector of the
first step (optionally with the multiplier if it is not 1) is drawn in the finder view.

Near the finder view these icon buttons are rendered:

- Next step (if there is the next step)
- Previous step (if there is the previous step)
- Cancel (returns to the previous context)

When we reach the final step, the position of the target object is marked.

### 5.3.2 Record Guide to Find the Object

The button is always rendered (regardless of whether a finding path already exists).
Clicking it opens the "Object Finding Paths" screen (5.12) in the context of the
currently searched object.

## 5.4 Search Object

The Search Object screen consists of:

- Search input
- Clear button (deletes the text typed so far)
- Cancel button (sends the user to the previous context)
- In-app keyboard (system keyboard must be supressed)
- Top search results (no paging)

When we start to type, it instantly displays (and refreshes) the most relevant results.
The search should be across object names and catalogue numbers.
Search results have the form "OBJECT_NAME (CONSTELLATION_NAME)". If
the match is by catalogue number, it should display CATALOGUE_NUMBER instead
of OBJECT_NAME. In case of search by catalogue number we need not to provide
catalogue name (e. g. "NGC 6543" is found even if we search for "6543").

For each search result there are the following icons:

- "Accept"
- "Details"
- "Finding Paths"

If we click on "Details", we are sent to "Object Details" screen.
If we click on "Accept" we are returned to the previous context and the view
is moved to bring the searched object to the center. "Finding Paths" lead to
the "Object Finding Paths" screen.

## 5.5 Observations

The screen displays expandable list of observations
by date (sorted in descending order). Expanding the date we can see
observation details and list of observed objects with all the details collected.
Observation header format is:

- `DATE, LOCATION (OBJECTS_OBSERVED)` when location name is available
- `DATE (OBJECTS_OBSERVED)` otherwise

For each observation there are icon buttons to:

- Edit observation metadata (date, location name, latitude/longitude, session notes)
- Delete observation (with confirmation dialog)
- Add object via search

For each object in the observation there are icon buttons to:

- Edit object-specific details (telescopes/eyepieces used, object notes)
- Delete object from observation (with confirmation dialog)

Object name/catalogue in the list opens the corresponding "Object Details" screen.

## 5.6 Telescopes

Contains a list of telescopes, for each of them storing:

- Name
- Focal length in mm
- Diameter in inches
- Whether it needs eyepiece (typically unchecked for binoculars)

and a list of eyepieces, for each of them storing:

- Name
- Focal length in mm
- FOV in degrees

The UI must enable to add, edit and delete telescopes and eyepieces. List of
defined telescopes and eyepieces should be expandable.

Note: Deletion of an eyepiece or a telescope that is used in an observation
must be prevented and a warning message should be displayed.

## 5.7 Finder Scope Quiz

At the beginning the quiz selects bright named stars. In each step it
displays star name and renders 4 finder views in a 2x2 matrix, each one
having a bright star in the center (one of those selected). The user
must select the finder view that corresponds to the star name. The rotation
of the view rendered in the finder has to be changed randomly.

Difficulty levels:

- Easy: stars up to magnitude 2
- Medium: stars up to magnitude 3
- Hard: stars up to magnitude 4

## 5.8 Constellation quiz

Before the beginning of the quiz constellations and constellations stars
(stars that are connected by the constellation lines) are selected according to
the difficulty level.

In each step a star from the selected set is chosen and a square sky fragment
is rendered with CONSTELLATION_QUIZ_FOV FOV (without constellation schemas,
randomly changing rotation) in such way that the target constellation
schema is in the center. The selected star is highlighted and four options
are displayed — each having a star name and the parent constellation.
The user is expected to choose the right combination. If the user answers incorrectly,
along with showing the correct answer the constellation lines are shown.

Difficulties:

- Easy: Only big constellations with bright stars, stars up to magnitude 2.
- Medium: Constellations with one bright star at least, stars up to magnitude 3.
- Hard: All constellations, stars up to magnitude 4.

## 5.9 Deep sky quiz

At the beginning the quiz selects the deep sky objects used according to
this guidelines:

- Easy: Select from 20 most bright deep sky objects
- Medium: Select from 50 most bright deep sky objects
- Hard: All deep sky objects

The quiz combines questions of more types:

### 5.9.1 Finder View

Same as the Finder Scope quiz, but for deep sky objects.

### 5.9.2 Image

Renders four deep sky images in a 2x2 matrix and lets the user select the image
corresponding to the displayed name or catalogue number (here catalogue
numbers are used only for objects without a nickname).

### 5.9.3 Object types

Displays an object name and four possible object types.

## 5.10 Find planet quiz

In each step the quiz renders a sky fragment with FIND_PLANET_QUIZ_FOV FOV
and randomly changing rotation. Then it adds a new point that does not correspond
to any star and it is not too close to a star of a similar or higher brightness.
Then it marks the added point and three other real stars with a similar
brightness, marking them with labels 1, 2, 3, 4. The user is expected
to reveal which point is not an existing star.

Difficulty levels:

- Easy: Added point is magnitude 1 or brighter
- Medium: Added point is magnitude 2 or brighter
- Hard: Added point is magnitude 4 or brighter

## 5.11 Moon Quiz

A Moon is rendered and a set of quiz objects is randomly selected. In each step
a crater or a mare is highlighted, four possible names of the highlighted
feature are displayed and the user is expected to select the right name. In
global mode all objects are taken into account, in local mode only the objects
near to the actual Moon terminator.

## 5.12 Object Finding Paths

### Data model

An object finding path consists of:

- A **path start** — a bright star (the anchor from which the first hop begins).
- A **sequence of steps**, where each step has:
  - a **start point** — always a star (or the target object for the final step)
  - an **end point** — any sky position (a star, or a memorable point between stars);
    the final step has no end point
  - an optional **multiplier** — how many times the vector is applied; must be a
    multiple of 0.5; vector × multiplier must not exceed 2× FINDER_FOV

The step name is derived from its start point. Step N+1's start point is the
same sky location as step N's effective end (start + (end − start) × multiplier),
but this is only an auto-fill — the user may override it.

Multiple paths may be defined for the same object, differing by path-start star,
but only one path per path-start star is allowed.

### Screen layout

The screen always has the context of the object for which paths are being defined
(set when opening the screen). It is opened from:

- The "Finding Paths" icon in search results (5.4)
- The "Record guide to find object" button in the Finder View (5.3.2)

UI elements:

a. A finder scope view (top portion of screen)
b. A step list (scrollable, below the finder)
c. A "+ Path" button in the header (hidden while recording a new path)

The finder scope view position does not change during list scrolling.

### Arrows in the finder

For any step that has both a start and an end point defined, an arrow is drawn in
the finder view from the start to the end. The arrow is clipped to the finder
circle boundary (it is not omitted just because part of it falls outside the
current view). If the multiplier is not 1×, the arrow is labeled "Nx".

All arrows for the active path are always visible, not only for the selected step.

### Recording a new path

Pressing "+ Path" opens a start-star search panel. After the user selects the path-
start star the header changes to:

  Path STAR_NAME ⇒ CAT_NUMBER (OBJECT_NAME)

The step list switches to recording mode, showing only the steps of the new path
being built (initially empty). The first step is added automatically.

### Selecting and editing a step

Only one step can be active (selected) at a time. Tapping a step in the list
selects it and centers the finder on the **anchor** for that step: the effective
end of the previous step (start + (end − start) × multiplier), or the path-start
star for step 1. The finder zoom resets to the standard FOV when a step is selected.

**Placing a pending point:**
While a step is active, the user can tap anywhere in the finder to place a cross
(the pending point). Tapping again moves the cross to the new tap position. The
user may freely pan and zoom the finder to position the cross precisely — zoom is
enabled in this mode and does not load higher-magnitude stars.

**Assignment buttons** (enabled only when a pending point exists):

- **Set start** — available for all steps except step 1; visible only when the
  pending point is within snap distance of a rendered star, in which case the
  position is snapped to the exact star location. Sets the step's start point,
  clears the pending cross, and resets the finder to standard FOV immediately.
- **Set end** — always available when a pending point exists (regardless of star
  proximity). Sets the step's end point, clears the pending cross, and resets
  the finder to standard FOV immediately.

**Multiplier button** — shown only when both start and end are defined. Clicking
it shows buttons 1×, 1.5×, 2×, … (up to the maximum allowed by vector length)
plus a Cancel button.

**Delete** — removes the selected step. No confirmation dialog is shown, but all
subsequent steps are silently deleted at the same time (see Cascade delete below).

**Set Final** — shown only when the target object falls within the current finder
view. Clicking it sets the target object as the step's start point, removes the
end point, and locks the step from further editing. This marks the path as complete.

### Auto-prefill of the next step's start

When step N's end point is a star and its multiplier is 1×, the next step's start
point is automatically filled with that star. The user may still override it with
"Set start".

### Cascade delete

Whenever any part of step N is changed (start, end, or multiplier) or step N is
deleted, all steps N+1, N+2, … are silently removed without confirmation. This
keeps the path internally consistent.

### Step labels

- A step with no start point set: "Step N"
- A step with a named star as start point: "Step N (STAR_NAME)"
- The final step (start = target object, no end point): "Step N (TARGET_NAME)"

## 5.13 Update object data

The screen displays date of the last synchronization / check and a
"Synchronize" button. Before fetching the data the server is asked for a hash
and that is compared with the current data hash to determine whether
synchronization is needed. If it is not needed the user is informed. The check
is done independently for object data and images. If the data are updated,
the progress bar is displayed during the download like in the Welcome screen.

## 5.14 Synchronize Observation Data

The screen is accessible from the menu at any time. If there are unsynchronized
changes in local observation data, the menu item shows the count as a badge.
The screen contains a survey of local changes to be synchronized and buttons
"Synchronize" and "Back".

After pressing "Synchronize", the app:

1. Pushes local observations to the server when local pending changes exist.
2. Pulls observations from the server and replaces local observation data.

Operation status is displayed in the screen.

## 5.15 About

The screen consists of:

- Application name and version date
- Short information about application
- Object data size (separately per object data, images and user data)
- Object statistics (number of stars, number of deep sky objects)
- Number of defined object finding paths
- Observation statistics (number of observations, number of observed objects,
  number of unique observed objects)
- back button

## 5.16 Object Details

The screen consists of:

- Object image (if available)
- All known object details
- Rise, transit and set times for the current date and location
- "Back" icon button
- "Observed" icon button — visually distinct (filled/checked state) if the object
  is already recorded in today's observation

In case of Moon we want to see the moon image in the current phase.
Information about phase % should be displayed for Moon and inner planets.

If we press "Observed" a new observation with current date and location will be
created (if it does not exist yet) or the existing data for today's observation
are updated (there is always at most one observation record, typically with multiple
observed objects, per date). A form consisting of the following items is
displayed:

- Date (prefilled with current date and time, but we can override it; if we override the
  date, the data are saved to observation of the overridden date)
- Location name (city / observing site, optional)
- Location (GPS coordinates, prefilled with the current GPS coordinates, with an option to clear it;
  clearing is appropriate when the observation form is filled in retrospectively
  and the current GPS position is no longer relevant)
- List of available telescopes, each with options (displayed as selectable
  exclusive icons):
  - Seen
  - Unseen (we tried to see the object in the instrument but we did not succeed)
    If we select "Seen" for a telescope that needs an eyepiece, optional selection
    of eyepieces is offered.
- Observation details (details related to the observation session, like
  weather, seeing conditions etc.)
- Object details
- Save button

Both details inputs are multiline text inputs, expandable as we type.
The text is entered using the in-app keyboard.

After pressing the "Save" button we are sent to the previous context.
