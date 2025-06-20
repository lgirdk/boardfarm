"""Compare images."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cv2
import numpy as np
from skimage.metrics import structural_similarity  # pylint: disable=no-name-in-module

if TYPE_CHECKING:
    from pathlib import Path

    from cv2.typing import MatLike

_LOGGER = logging.getLogger(__name__)

# ruff: noqa: RUF100
# pylint: disable=no-member
# flake8: noqa: RST219, RST305


def _append_qualifier(filename: Path, qualifier: str) -> str:
    return str(filename.with_stem(f"{filename.stem}_{qualifier}"))


def _build_mask(
    image: MatLike, ignore_areas: list[tuple[int, int, int, int]]
) -> MatLike:
    mask = np.full(image.shape[:2], 255, dtype="uint8")
    for xtop, ytop, xbottom, ybottom in ignore_areas:
        cv2.rectangle(
            mask,
            (xtop, ytop),
            (xbottom, ybottom),
            0,
            -1,
        )
    return cv2.bitwise_and(image, image, mask=mask)


def compare_images(  # noqa: PLR0915  # pylint: disable=too-many-locals,too-many-statements
    first_image: Path,
    second_image: Path,
    ignore_areas: list[tuple[int, int, int, int]] | None,
    show_images: bool = False,
) -> dict[str, np.float64]:
    """Compare 2 images and return the similarity score.

    :param first_image: Usually the original image (usually a png)
    :type first_image: Path
    :param second_image: The new image (with same size as the first image)
    :type second_image: Path
    :param ignore_areas: A list of coordinates for the zones (rectangles) to be
                         ignored during the comparison (xtop, ytop, xbottom, ybottom)
                         1 tuple is one rectangle.

                         (xtop, ytop)
                              |-----------------|
                              |                 |
                              |                 |
                              |-----------------|(xbottom,ybottom)

    :type ignore_areas: list[tuple[int, int, int, int, int]] | None
    :param show_images: shows the images, NOT TO BE USED in CI, defaults to False
    :type show_images: bool
    :return: the similarity Score of the original images if there is no ignore_areas
             otherwise returns the masked images similarity score
    :rtype: np.float64
    """
    masked_score = None
    first = cv2.imread(str(first_image.absolute().resolve()))
    second = cv2.imread(str(second_image.absolute().resolve()))
    first_masked = None
    second_masked = None

    # this needed for the structural_similarity comparison
    first_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    second_gray = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)

    # this is the % of similarity between the 2 original images (i.e. unmasked)
    # NB: the images MUST BE of the SAME SIZE!!!!
    unmasked_score, unmasked_diff = structural_similarity(  # type: ignore[no-untyped-call]
        first_gray,
        second_gray,
        full=True,
    )
    msg = f"Unmasked Similarity Score: {unmasked_score * 100:.3f}%"
    _LOGGER.info(msg)
    diff = unmasked_diff = (unmasked_diff * 255).astype("uint8")

    # same as above but on the masked images (if any areas are to be ignored)
    if ignore_areas:
        # these are the same images with the areas to be ignored blacked out
        first_masked = _build_mask(first, ignore_areas)
        second_masked = _build_mask(second, ignore_areas)
        masked_score, masked_diff = structural_similarity(  # type: ignore[no-untyped-call]
            cv2.cvtColor(first_masked, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(second_masked, cv2.COLOR_BGR2GRAY),
            full=True,
        )
        msg = f"Masked Similarity Score: {masked_score * 100:.3f}%"
        _LOGGER.info(msg)

        # The diff image contains the actual image differences between the two images
        # and is represented as a floating point data type so we must convert the array
        # to 8-bit unsigned integers in the range [0,255] before we can use it with OpenCV
        diff = (masked_diff * 255).astype("uint8")

    # Threshold the difference image, followed by finding contours to
    # obtain the regions that differ between the two images
    thresh = cv2.threshold(
        unmasked_diff,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )[1]
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) == 2:  # noqa: PLR2004, SIM108
        contours = contours[0]  # type: ignore[assignment]
    else:
        contours = contours[1]  # type: ignore[assignment, unreachable]

    # Highlight differences
    mask = np.zeros(first.shape, dtype="uint8")
    filled = second.copy()

    for c in contours:
        area = cv2.contourArea(c)  # type: ignore[arg-type]
        if area > 100:  # noqa: PLR2004
            x, y, w, h = cv2.boundingRect(c)  # type: ignore[arg-type]
            cv2.rectangle(first, (x, y), (x + w, y + h), (36, 255, 12), 2)
            cv2.rectangle(second, (x, y), (x + w, y + h), (36, 255, 12), 2)
            cv2.drawContours(mask, [c], 0, (0, 255, 0), -1)  # type: ignore[list-item]
            cv2.drawContours(filled, [c], 0, (0, 255, 0), -1)  # type: ignore[list-item]

    cv2.imwrite(_append_qualifier(first_image, "contour"), first)
    cv2.imwrite(_append_qualifier(second_image, "contour"), second)
    cv2.imwrite(_append_qualifier(second_image, "diff"), diff)
    cv2.imwrite(_append_qualifier(second_image, "mask"), mask)
    cv2.imwrite(_append_qualifier(second_image, "filled"), filled)
    if first_masked is not None:
        cv2.imwrite(_append_qualifier(first_image, "masked"), first_masked)
    if second_masked is not None:
        cv2.imwrite(_append_qualifier(second_image, "masked"), second_masked)

    # NB: cv2.waitKey() is interactive and shold not be used in CI environments
    # but you knew that already 😁!
    if show_images:
        cv2.imshow("first", first)
        cv2.imshow("second", second)
        cv2.imshow("diff", diff)
        cv2.imshow("mask", mask)
        cv2.imshow("filled", filled)
        if first_masked is not None:
            cv2.imshow("first_masked", first_masked)
        if second_masked is not None:
            cv2.imshow("second_masked", second_masked)
        cv2.waitKey()

    return (
        round(unmasked_score * 100, 3)
        if masked_score is None
        else round(masked_score * 100, 3)
    )
