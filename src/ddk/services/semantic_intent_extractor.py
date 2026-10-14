"""SemanticIntentExtractor — LLM-powered UI intent extraction (INGEST-04)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models.config import DEFAULT_PRIMARY_MODEL
from ddk.models.input import CaseInput
from ddk.models.intent import IntentGraph
from ddk.services.images import encode_design_image

_SYSTEM_PROMPT = """You are an expert UI analyst. Your job is to analyze UI
screenshots or mockups and extract a precise structural representation of the
interface.

You must output a valid JSON object conforming to the IntentGraph schema.
Do not include any explanation outside the JSON.

## IntentGraph Rules

### LayoutRegion extraction
- Identify every distinct visual region: header, nav, sidebar, main content,
  footer, cards, modals, forms, tables, hero sections, CTAs, list views.
- Assign bounding boxes as relative coordinates (0.0 to 1.0).
- A region that contains others must list their IDs in `children`.
- `semantic_label` is a 1~5 word Korean or English label describing the region's purpose.

### ComponentSpec extraction
- Extract every interactive or semantic component: Button, Input, Card, Table,
  Badge, Icon, etc.
- `component_type` must be a PascalCase React-compatible component name.
- `props` should capture visible text content, variant hints, and disabled states.
- Assign `confidence` based on how clearly identifiable the component is
  (1.0 = clearly a known pattern).

### InteractionSpec extraction
- Only include interactions that are visually implied (buttons, links, form submits).
- `trigger` must be one of: click, hover, focus, submit, change, keydown, scroll.
- `action` must be one of: navigate, open-modal, close-modal, submit-form,
  toggle, filter, sort, load-more, other.

### Confidence scoring
- 1.0 = unambiguous standard component
- 0.7~0.9 = likely but uncertain
- <0.7 = low confidence, list in `unresolved_items`

## Critical constraints
- Do NOT hallucinate components that are not visible in the image.
- If an element is unclear, lower its confidence and add a description to `unresolved_items`.
- Maximum 50 components per image. If more are present, group minor ones."""


class SemanticIntentExtractor:
    """Extracts IntentGraph from UI screenshots via Claude vision (sonnet)."""

    def __init__(self, llm: LLMAdapter, model: str = DEFAULT_PRIMARY_MODEL) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model=model,
            temperature=0.0,
            max_tokens=8192,
            effort="medium",
        )

    async def extract(self, case_input: CaseInput) -> IntentGraph:
        """Extract UI intent from the first image in case_input.

        Args:
            case_input: Contains image_paths, prompt, case_id.

        Returns:
            Validated IntentGraph with layout, components, interactions.
        """
        image_path = case_input.image_paths[0]
        image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()[:16]
        image_b64, media_type = encode_design_image(image_path)

        user_content = (
            f"Analyze this UI image and extract the IntentGraph.\n\n"
            f"User's intent description:\n{case_input.prompt}"
        )
        if case_input.reference_notes:
            user_content += f"\n\nAdditional context: {case_input.reference_notes}"
        user_content += "\n\nOutput the complete IntentGraph JSON object."

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(
                role="user",
                content=user_content,
                images=[(image_b64, media_type)],
            ),
        ]

        response: LLMResponse = await self._llm.complete_structured(
            messages, self._config, output_schema=IntentGraph
        )

        data: dict[str, Any] = json.loads(response.content)
        # Inject required fields that come from our context, not LLM
        data["id"] = case_input.case_id
        data["source_image_hash"] = image_hash
        # Ensure defaults for optional lists
        data.setdefault("layout_regions", [])
        data.setdefault("components", [])
        data.setdefault("interactions", [])
        data.setdefault("unresolved_items", [])
        data.setdefault("confidence", 0.5)

        return IntentGraph.model_validate(data)
