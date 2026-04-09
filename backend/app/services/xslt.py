"""XSLT transformation service.

Provides apply_xslt() as the single entry point for XML→HTML transformations.
Currently supports lxml (XSLT 1.0). Saxon (XSLT 2.0/3.0) is stubbed and will
be wired in a future phase when the saxonpy dependency is available.
"""

from __future__ import annotations

import re

from lxml import etree


def apply_xslt(xslt_content: str, xml_bytes: bytes, processor: str = "lxml") -> str:
    """Transform *xml_bytes* with *xslt_content* and return body inner HTML.

    Args:
        xslt_content: XSLT stylesheet as a UTF-8 string.
        xml_bytes:    Source XML document as bytes.
        processor:    ``"lxml"`` (XSLT 1.0) or ``"saxon"`` (XSLT 2.0/3.0,
                      not yet implemented).

    Returns:
        The inner HTML of the ``<body>`` element produced by the transform,
        or the full transform output string when no ``<body>`` is found.

    Raises:
        ValueError: when *processor* is not a recognised value.
        NotImplementedError: when processor is ``"saxon"`` (future feature).
    """
    if processor == "lxml":
        return _apply_lxml(xslt_content, xml_bytes)
    if processor == "saxon":
        return _apply_saxon(xslt_content, xml_bytes)
    raise ValueError(f"Unknown XSLT processor: {processor!r}")


def _apply_lxml(xslt_content: str, xml_bytes: bytes) -> str:
    """Apply an XSLT 1.0 stylesheet via lxml and return body inner HTML."""
    # Both inputs come from trusted Designer sources (eXist-db + admin upload).
    xslt_doc = etree.fromstring(xslt_content.encode())  # noqa: S320
    transform = etree.XSLT(xslt_doc)
    xml_doc = etree.fromstring(xml_bytes)               # noqa: S320
    result_str = str(transform(xml_doc))
    body_match = re.search(
        r"<body[^>]*>(.*?)</body>", result_str, re.DOTALL | re.IGNORECASE
    )
    return body_match.group(1) if body_match else result_str


def _apply_saxon(xslt_content: str, xml_bytes: bytes) -> str:  # noqa: ARG001
    """Saxon (XSLT 2.0/3.0) — not yet implemented.

    To enable: add ``saxonpy`` to requirements.txt and replace this body
    with the appropriate Saxon-HE Python API calls.
    """
    raise NotImplementedError(
        "Saxon processor is not yet configured. "
        "Add saxonpy to requirements.txt and implement _apply_saxon()."
    )
