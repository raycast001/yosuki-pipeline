# Open Technical Q&A Prep — 10–15 Minutes
## Architecture, Alternatives, Adobe Enterprise, Scaling

---

## How to Use This Doc

These are questions they're likely to ask. For each one there's a short answer
you can say out loud, plus bullet points if you want to go deeper.
Don't memorise — just read through these once so the ideas are fresh.

---

## ARCHITECTURE QUESTIONS

---

**Q: Why did you use a JSON file (brief.json) as the creative brief instead of a database or a UI form?**

> "For a take-home pipeline, a JSON file is the right level of complexity — it's human-readable, version-controllable, and every script can import it directly. In a production system you'd probably back it with a database and a UI, but the architecture is the same: one source of truth that drives everything downstream. brief.json is the prototype of that."

---

**Q: Why did you separate copy preview (02b) from apply (02c) instead of applying in one step?**

> "The preview step is a creative checkpoint. A copywriter or creative director can review what Claude generated before it's ever applied to a render. If they don't like it, re-run 02b — Claude gives fresh output. The two-step design means no render ever runs with unapproved copy. In a real production workflow you'd surface that preview in a UI with an approve/reject button."

---

**Q: Why does variants.json track status? Why not just check if the file exists on disk?**

> "File-based state is fragile — a partial render might leave a corrupt MP4 that looks like a completed render. variants.json tracks status explicitly: `pending`, `copy_generated`, `rendered`. You can also query it: 'how many have rendered, how many are waiting, which ones failed.' It's also tracked in git — so the repo shows the pipeline's state at time of commit, not just the code."

---

**Q: How does the crash recovery work in practice?**

> "03_populate_templates.py saves variants.json after every single successful render inside the loop — not just at the end. So if aerender crashes on variant 30, variants 1–29 already have status 'rendered'. Re-run the pipeline — the idempotency check skips anything with status 'rendered' and picks up from variant 30. No manual intervention, no re-rendering completed work."

---

**Q: Why aerender instead of the After Effects render queue?**

> "aerender is the command-line version of After Effects' render engine. It's made for exactly this — batch rendering without a GUI. The render queue requires a human to click 'render.' aerender accepts a project path, comp name, and output path, and runs headlessly. That's what makes batch automation possible."

---

## AI / MODEL QUESTIONS

---

**Q: Why Flux instead of Stable Diffusion, Midjourney, or DALL-E?**

> "Flux has the best ControlNet support for structured composition — specifically Flux Canny ControlNet, which is what this pipeline uses. Midjourney doesn't have a ControlNet equivalent. DALL-E doesn't have a local API. Stable Diffusion has ControlNet but the Flux results are noticeably sharper and more photorealistic at 1920×1080. For a pipeline that needs spatial consistency across 100+ renders, Flux + Canny was the clear choice."

---

**Q: What are the Canny thresholds doing and how did you pick 0.05 / 0.10?**

> "Canny is an edge detection algorithm. Low threshold controls the minimum edge strength to detect — lower means more edges captured. High threshold is the cutoff above which an edge is always kept. At 0.05/0.10 you get the main structural lines — floor, walls, geometry — without noise from texture or lighting gradients. I tested a range: 0.03/0.08 was too tight and made Flux produce stiff, over-constrained images. 0.15/0.30 was too loose and lost the spatial consistency. 0.05/0.10 is the balance point."

- Lower values = tighter constraint, less Flux creativity
- Higher values = looser constraint, more variation, less consistency
- The C4D greyscale render (no textures) helps a lot — Canny gets clean geometric edges

---

**Q: Why Claude for copy and not GPT-4 or Gemini?**

> "Honest answer: I know Claude's API well, and the brief was from an Anthropic-adjacent context. Technically, any frontier model would work — the prompts are structured and the output format is enforced JSON. Claude handles the multilingual constraints well out of the box — German compound word brevity, Japanese tone and syllable awareness. That's not unique to Claude but it worked reliably."

---

**Q: How do you ensure Claude doesn't hallucinate wrong copy or break the JSON format?**

> "Two layers. First, the prompt is explicit: 'Return ONLY a valid JSON array, no markdown, no explanation.' Second, the response is immediately passed to `json.loads()` — if it's not valid JSON, the script crashes loudly rather than silently applying bad copy. In production you'd add retry logic with a fallback prompt, but for this pipeline a loud failure is better than a silent bad render."

---

**Q: How would you add video — text-to-video or image-to-video?**

> "The ComfyUI workflow folder already has video workflow JSONs in it — I explored LTX-2 image-to-video. The architecture is the same: inject a still frame as the input image, post the workflow to ComfyUI, poll for the output video file. The difference is the output is an MP4 instead of a PNG, and you'd link it into After Effects as a video layer instead of a still image. The pipeline structure doesn't change — just the workflow JSON and the output file type."

---

## ADOBE ENTERPRISE QUESTIONS

---

**Q: How would this work in an Adobe enterprise context — Firefly, Frame.io, Creative Cloud?**

> "A few integration points:
>
> **Adobe Firefly API** — Firefly is Adobe's generative AI, built into Creative Cloud. You could replace the ComfyUI/Flux background generation step with Firefly API calls. The pipeline structure stays identical — instead of `requests.post(COMFYUI_URL/prompt)` you'd call the Firefly generate endpoint. Firefly has the advantage of being commercially safe (trained on licensed content), which matters at enterprise scale.
>
> **After Effects + Motion Graphics Templates (.mogrt)** — For enterprise AE workflows, .mogrt files are the standard. They expose parameters (text, images, colours) as a clean API that doesn't require ExtendScript. The pipeline could populate .mogrt files instead of .aep files — that's a more robust long-term approach and plays better with Adobe's ecosystem.
>
> **Frame.io** — For review and approval. The copy preview step (02b → 02c) maps naturally onto Frame.io's review workflow: upload the preview renders, get annotations and approvals, then trigger 02c to apply. Adobe acquired Frame.io specifically for this kind of production pipeline integration.
>
> **Creative Cloud Libraries** — Brand assets (product cutouts, fonts, colour palettes) could be sourced from a CC Library instead of a local folder. That's the enterprise-grade asset management layer."

---

**Q: What would the Adobe-native version of this pipeline look like without Python?**

> "You could build a version of this entirely within the Adobe ecosystem:
> - **After Effects + Motion Graphics Templates** for the templating layer
> - **Adobe Firefly** for background generation (via API or built into AE)
> - **Adobe Express** or **InDesign** for static asset variants
> - **Frame.io** for review/approval workflow
> - **Adobe Workfront** for campaign management and scheduling
>
> The Python pipeline is a custom orchestration layer that connects tools that don't natively talk to each other. An all-Adobe stack would have tighter integration but less flexibility — you'd be locked into what each Adobe product exposes. The Python approach lets you swap any component: different AI model, different renderer, different delivery target."

---

**Q: How would this integrate with a Digital Asset Management (DAM) system?**

> "The delivery step (05_deliver.py) is currently a simple file organiser — it copies renders into a local folder structure. In an enterprise context, you'd replace or extend that step with API calls to a DAM: upload the render, set metadata (product ID, market, ratio, campaign, date), tag with the relevant taxonomy. Systems like Bynder, Widen, or Adobe Experience Manager all have REST APIs. The pipeline already has all the metadata in variants.json — the product ID, market, ratio, copy — it's just a matter of pushing that to the DAM alongside the file."

---

## SCALING QUESTIONS

---

**Q: How would this scale to 500 products or 20 markets?**

> "The pipeline scales horizontally. Right now it's single-threaded — one render at a time. For larger scale:
> - **Parallel ComfyUI jobs** — ComfyUI has a built-in queue. You can POST all jobs at once and it processes them in parallel if you have multiple GPUs.
> - **Parallel aerender** — multiple aerender instances can run simultaneously on different cores.
> - **Cloud rendering** — aerender can run on AWS or Azure with an Adobe floating license. You'd spin up instances per render batch.
> - **brief.json stays the same** — the data model scales cleanly. 500 products is just a longer list in brief.json."

---

**Q: What are the failure modes and how do you handle them?**

> "Three main ones:
>
> **ComfyUI generation failure** — the `find_output()` function has a timeout (300 seconds by default). If it times out, it raises an exception and the job is logged as failed. The background file won't exist, and the render step will catch the missing file.
>
> **aerender crash** — handled by the per-render save in 03_populate_templates.py. Each successful render is persisted immediately. Failures are logged with the variant ID. The pipeline finishes and reports a count of successes vs failures.
>
> **Claude API failure** — `json.loads()` on the response will raise an exception if Claude returns malformed output. The script exits with an error before any copy is written. In production you'd add retry logic."

---

**Q: What would you do differently if you were building this for production, not a take-home?**

> "A few things:
> - **.mogrt templates** instead of raw .aep files for the AE side — more maintainable, no ExtendScript fragility
> - **A proper job queue** (Celery, or even just a SQLite-backed queue) instead of variants.json as state — more robust for concurrent runs
> - **Firefly API** instead of local ComfyUI for the background generation — commercially licensable, no local GPU required, scales to cloud
> - **Frame.io integration** for the copy review step — instead of a terminal preview, reviewers see annotated renders
> - **Tests** — at minimum a smoke test that validates brief.json parses correctly and all config paths resolve before any expensive API calls are made"

---

## GENERAL / OPEN-ENDED

---

**Q: What part of this are you most proud of?**

> "The ControlNet approach — using Cinema 4D as a digital twin to generate a greyscale scene render, then using Canny edge detection to constrain Flux to that spatial layout. It solves a real problem: without it, AI-generated backgrounds are beautiful but spatially inconsistent. With it, every background has the same floor plane and camera angle, so the product cutout always looks like it belongs in the scene. That's the part that makes this feel like production quality rather than a demo."

---

**Q: What would you tackle next if you had more time?**

> "Two things. First, video — the pipeline generates stills, but the architecture supports video. LTX-2 or Kling for the background animation, then composite the product over it in AE. The ComfyUI workflow JSON for that is already in the repo.
>
> Second, I'd add a proper review UI — right now the copy preview is a terminal printout. In production, a creative director should see the copy in context: rendered on the actual ad template, with approve/reject buttons. That's a Streamlit or web UI extension of what's already there."
