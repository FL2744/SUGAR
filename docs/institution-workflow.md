# From collected items to a source-backed picture

SUGAR's research workbench collects evidence. The institution workflow turns that evidence into records an analyst can
verify, map, compare and keep current. Each step keeps the source and says who decided what.

```
collect → find names → record with sources → verify claims → place on map → compare networks → monitor → brief
```

## 1. Collect
Social platforms, plus sources that need no account: Wikipedia, news coverage (GDELT), scholarly works (OpenAlex), feeds
you list (RSS/Atom) and **websites you name**. The web reader honours `robots.txt`, reads one page per site per second,
refuses non-public addresses (including after redirects), and follows the news and event pages a site links to.

## 2. Find institutions
*Institutions → Find in a run* proposes institution names with the sentence each came from. Patterns always run; your AI
model adds suggestions only when you choose it, and a suggestion is dropped unless its quote appears word for word in the
item. You can also add an institution directly, with a source address, or use an item as evidence from its Provenance panel.

## 3. Record with sources, then verify
Records live in the evidence-backed registry. Every field is a *claim* with evidence and a review state. A person verifies,
rejects or flags each claim; verified claims show who and when. If two sources disagree, the field stays unresolved until a
person decides. **Confidence** (high, medium, low) says how well supported a record is (independent sources, human
verification, conflicts). It is not a measure of importance or influence. Merging duplicates moves their claims; nothing
is deleted.

## 4. Closures, renames and moves
Status history is kept (active, closed, renamed, relocated, unknown) with dates and sources. *Check captured history of its
pages* asks the Internet Archive when a page last responded and whether it changed. A page that stops responding is a lead
to check, not proof of a closure.

## 5. Networks, maps and overlap
A **network** is a label on institutions with a role: *subject* (being studied) or *reference* (to compare against).
Import a published directory (you confirm the column mapping first) or search Wikidata and OpenStreetMap for candidates.
The **Map** shows both networks, closed sites in grey, low-confidence records with a ring, and optional activity heat. *Overlap*
computes the distance from each subject institution to the nearest reference institution and which recorded audiences and
programs they share. These are computed facts about the records, not findings of influence, competition or causation.

## 6. Activity and audiences
*Code activity and audiences* proposes audiences, programs, activity types and **reported attendance** for each item, with a
quote, using a multilingual phrase list (and your model if chosen). A person confirms or rejects each proposal; only confirmed
labels can be added to an institution, and they cite the item. Attendance is "as reported by the source".

## 7. Monitor
*Monitoring* repeats the project's plan on a schedule (hourly to monthly). Each pass flags new and changed items and ends with a
digest of institution changes: new records, closures, reopenings, renames, moves, new programs or audiences, and sources that
could not be read. Scheduled passes run while SUGAR is open (or on the server it is connected to) and never start while
another run is active.

## 8. Judge relevance, see themes, write the brief
*Check relevance* scores each item with reasons; *Mark likely off-topic* applies "not relevant" in one confirmed step, to items
no person has judged. *Show themes* groups items by shared distinctive words. *Create brief* writes a Markdown and Word brief:
question and scope, what was and was not read (with each source's limits), institutions with confidence, last-verified date and
numbered sources, confirmed activity, overlap, changes, themes, review progress, and the method. An optional model summary is
kept sentence by sentence only when each sentence cites a real numbered source.

## 9. Reuse the method
*Reuse a method* exports networks, plan, extra search vocabulary, websites and feeds, audience/program wording, relevance terms,
optional starting institutions (each with a source) and monitor schedules as a JSON **profile**. Applying a profile to another
project reproduces the method for another region or network. Profiles never contain credentials or collected items and are
imported at run time, so study-specific detail is data, not program code.

## Measuring accuracy
*Accuracy check* gives a random sample to label, without suggestions shown, then reports precision, recall and F1 for
relevance, audiences and programs. Repeat it after changing a model, vocabulary or source.

## What this does not do
It does not decide that an institution is influential, hostile or effective. It does not treat a social-media sample as
representative, or reach figures as verified. Coverage gaps (a source that was blocked, a platform that returns only recent
posts) are stated in every brief.
