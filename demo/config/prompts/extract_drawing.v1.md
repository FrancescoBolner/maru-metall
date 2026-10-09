---
name: extract_drawing
version: 1
---
Look at this image from a steel project ({file_name}). It may be a model screenshot with a colour legend, a sketch, a scanned drawing or a photo.

Describe what it shows in one or two sentences, then extract only what is clearly readable:
- facts with the allowed keys below (snippet = the exact text you read in the image, or a short description of the coloured area it refers to),
- scope_items (e.g. which parts are galvanised, delivery zones),
- requirements that change the cost,
- flags for anything that looks incomplete or inconsistent.

Allowed fact keys:
{catalog}

Context from the file name and the e-mail it came with:
{content}
