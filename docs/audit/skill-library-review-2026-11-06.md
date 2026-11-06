# Skill library review (2026-11-06)

Imported 188 public video skills (OpenMontage, HyperFrames, Remotion, Vox Director, Video Toolkit, HeyGen, Varg) next to the 56 existing ones, then had 8 parallel reviewers (Sonnet) read every SKILL.md: keep/delete, category, Vietnamese guide (purpose / when / benefit / requires / paid) stored in `metadata.guide`.

Result: 244 reviewed, 29 deleted, 215 kept. Paid: 65.

Kept by category: video 58, motion 41, dev 26, workflow 24, image 17, marketing 16, audio 14, design 11, docs 7, other 1

Originals are kept in `D:\Code\Documents\skills`; existing (git-tracked) skills were never deleted.

## Deleted

| Skill | Reason | Duplicate of |
|---|---|---|
| ai-video-gen | Router for OpenMontage-internal tools (video_selector, seedance_video) that do not exist in AgentDev; provider-specific skills cover the real content. | seedance-2-0 |
| atlas-cloud | Depends on OpenMontage tool wrappers absent from AgentDev; mostly a model/price table for one gateway. |  |
| avatar-video | Uses HeyGen v2 endpoints that the newer heygen-video skill explicitly declares outdated; superseded. | heygen-video |
| comfyui | Written for OpenMontage comfyui_* tools that do not exist in AgentDev, so its instructions are not usable here. |  |
| create-video | Older HeyGen skill superseded by heygen-video, which covers the v3 Video Agent pipeline more completely. | heygen-video |
| faceswap | Face swapping real people risks non-consensual or deceptive content; ethically dubious. |  |
| heygen | Marked [DEPRECATED] in its own description and superseded by heygen-video and heygen-avatar. | heygen-video |
| how-to-make-ai-video | Thin search-router to an external registry, no real instructions of its own. |  |
| kling-official | Internal developer notes for OpenMontage provider code (tools/_kling), not usable instructions in AgentDev. | kling-4-prompting |
| ltx2 | Relies on tools/ltx2.py and a self-deployed Modal endpoint, neither present, so the instructions are unusable. |  |
| make-a-woke-profile-with-chatgpt | Novelty meme trend with political satire; off-topic for a professional production pipeline. |  |
| pose-library-design | Thin stub tied to unnamed pose_library artifacts; little actionable content. |  |
| provider-model-refresh | Dated provider-refresh maintenance note tied to OpenMontage tool names, not reusable guidance. |  |
| provider-refresh-oct23 | Dated one-off provider refresh note that will go stale. |  |
| remotion-docs | Thin lookup recipe duplicating what best-practices and web fetch already cover; embeds a third-party search key. | remotion-best-practices |
| remotion-license | Only three links and a purchase URL, no actionable instructions. |  |
| remotion-studio | Thin; fully covered by remotion-best-practices and remotion-create. | remotion-best-practices |
| remotion-upgrade | One-off dependency-maintenance procedure rather than reusable production guidance. |  |
| reverse-any-video | Thin dispatch relying on a proprietary paid HyperFrames Pro command and copying existing videos; low general value. |  |
| runpod | Relies on missing toolkit scripts (tools/*.py --setup) and is infrastructure housekeeping. |  |
| setup-api-key | Single-provider setup housekeeping; AgentDev uses logged-in CLI accounts, not API keys. |  |
| style-sampling | Thin dispatcher needing paid HyperFrames Pro templates pulled from a server, plus a telemetry beacon. |  |
| text-to-speech | Thin stub that defers to a missing, dated 'provider-refresh-oct23' skill. |  |
| varg-character-beautiful-woman | Glamour-model prompting that includes wording to bypass moderation blocks; ethically dubious and low professional value. |  |
| varg-character-fitness | Core value is wording tuned to bypass image-model moderation; niche and ethically dubious. |  |
| varg-publish-skill | Publishing a skill to an external registry; irrelevant to producing work. |  |
| video-skills | Merely a search finder for the varg.ai how-to registry (external lookup) with no instructions of its own; not useful locally. |  |
| video-toolkit | Depends on a fixed ~/.openclaw toolkit path, Modal/RunPod GPUs and darwin/linux only; unusable here without external setup. |  |
| web-design-guidelines | Thin stub that only fetches a remote rules file; no instructions of its own and needs network. | impeccable |

## Flagged but kept (existing library skills)

| Skill | Reviewer reason | Why kept |
|---|---|---|
| high-end-visual-design | Persona-style overlap with design-taste-frontend and impeccable; overblown and less complete. | existing curated skill; user decides |
| debugging-and-error-recovery | Overlaps heavily with systematic-debugging, which is more complete (root-cause tracing, defense in depth, helper scripts). | referenced by 4 kept skills |
| python-scratchpad | Thin stub depending on an execute_code tool; little instruction value. | uses AgentDev execute_code tool |
| rest-api-caller | Thin stub depending on execute_code; generic knowledge the agent already has. | uses AgentDev execute_code tool |
| find-skills | Installs external skills from a public registry; not useful inside a curated skill library. | existing curated skill; user decides |
| using-superpowers | Pack-internal meta rule for the superpowers set; depends on skills and runtimes outside this library. | referenced by executing-plans, writing-skills |
| research | A 12-line stub with three generic steps; no real instructions. | existing curated skill; user decides |

## Lowest rated kept (quality <= 3)

- gemini-omni (3): Useful prompting and editing guidance, though written around OpenMontage tool names.
- grok-media (3): Short but accurate portable API reference with pricing and prompt tips.
- minimax-h3 (3): Short but accurate routing guide with prompting advice for a current video model.
- remotion (3): Partly tied to a toolkit lib not present here, but motion-craft guidance is valuable.
- remotion-multimedia (3): Small but accurate helpers with code files present.
- remotion-saas (3): Official guidance with three reference files; narrower use case.
- remotion-to-hyperframes (3): Concrete migration procedure with lint script and references.
- slideshow (3): Clear, specific skill with references for a distinct deliverable.
- synthetic-screen-recording (3): Good decision guide, though the TerminalScene component lives in an external toolkit.
- synthetic-ui-demo (3): Useful method; example folders referenced are missing but the technique is explained.
- varg-character-absurd (3): Short but actionable recipe within the varg character-design family.
- varg-character-big-guy (3): Actionable, tested prompt details and respectful framing rule.
- varg-character-cringe (3): Niche but concrete character recipe and posting format.
- varg-character-grandma (3): Concrete recipe with details, clothing and prop guidance.
- video-download (3): Simple but practical yt-dlp command reference; respect copyright when using.
- dashscope (3): Concise, accurate API notes for three useful media endpoints.
- qwen-edit (3): Useful prompting patterns, but depends on a toolkit script not in this folder.
- acestep (3): Detailed and useful, though tied to a toolkit script.
- azure-speech-to-text (3): Solid provider-specific STT reference.
- azure-text-to-speech (3): Solid provider-specific TTS reference.
- doubao-tts (3): Short but accurate, includes the key auth gotcha.
- fish-audio-tts (3): Short, accurate provider notes.
- varg-character-keynote (3): Narrow but concrete working template for a short ad format.
- 3d-asset-generation (3): Useful routing table, though partly tied to toolkit tools.
- character-animation-qa (3): Short but actionable QA checklist.
- framer-motion (3): Concise, practical code per principle; useful for React motion.
- lottie-bodymovin (3): Practical but narrow; companion to framer-motion principles.
- svg-character-animation (3): Short but correct; pivot and frame-driving tips are useful.
- threejs-world-generation (3): Detailed method, but depends on an external threejs_world tool that may be absent.
- varg-dropship-reel (3): Niche but complete with scripts; other skills depend on its captions script.
- varg-mascot-jingle-ad (3): Creative, specific workflow; moderate depth.
- figma (3): Specialized but real workflow with verification script.
- high-end-visual-design (2): Persona-style overlap with design-taste-frontend and impeccable; overblown and less complete.
- pr (3): Compact but useful PR template.
- python-scratchpad (2): Thin stub depending on an execute_code tool; little instruction value.
- rest-api-caller (2): Thin stub depending on execute_code; generic knowledge the agent already has.
- agents (3): Concrete ElevenLabs agents setup with CLI/SDK examples and references; niche but usable.
- find-skills (2): Installs external skills from a public registry; not useful inside a curated skill library.
- handoff (3): Short but actionable handoff recipe.
- using-superpowers (2): Pack-internal meta rule for the superpowers set; depends on skills and runtimes outside this library.
- research (2): A 12-line stub with three generic steps; no real instructions.
