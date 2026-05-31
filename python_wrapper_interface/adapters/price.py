"""Price encoding/decoding utilities.

All conversions use the project-wide ``PRICE_SCALE`` constant from
:mod:`python_wrapper_interface.types`.
"""

from __future__ import annotations

from decimal import Decimal

from python_wrapper_interface.types import PRICE_SCALE

SCALE_DIGITS: int = 4
"""Number of decimal digits implied by ``PRICE_SCALE``."""


def to_scaled(value: Decimal, scale: int = PRICE_SCALE) -> int:
    """Convert a decimal price to a scaled integer.

    Parameters
    ----------
    value : Decimal
        The price as an exact decimal.
    scale : int
        Scale factor (default ``PRICE_SCALE``).

    Returns
    -------
    int
        ``round(value * scale)``.
    """
    return int(value * scale)


def from_scaled(scaled: int, scale: int = PRICE_SCALE) -> Decimal:
    """Convert a scaled integer back to a Decimal price.

    Parameters
    ----------
    scaled : int
        Scaled price.
    scale : int
        Scale factor (default ``PRICE_SCALE``).

    Returns
    -------
    Decimal
    """
    return Decimal(scaled) / Decimal(scale)


def decode_mantissa_exp(
    mantissa: int,
    exp: int,
    scale_digits: int = SCALE_DIGITS,
) -> int:
    """Decode a ``{mantissa, exponent}`` price into a scaled integer.

    The formula is ``mantissa * 10^(scale_digits + exp)``.

    Parameters
    ----------
    mantissa : int
        Mantissa component.
    exp : int
        Exponent component (typically <= 0).
    scale_digits : int
        Number of digits in the scale factor (default 4).

    Returns
    -------
    int
        Price as a scaled integer compatible with ``PRICE_SCALE``.
    """
    power = scale_digits + exp
    if power >= 0:
        return mantissa * (10 ** power)
    return mantissa // (10 ** (-power))


def encode_mantissa_exp(
    scaled: int,
    scale_digits: int = SCALE_DIGITS,
) -> tuple[int, int]:
    """Encode a scaled-integer price as ``{mantissa, exponent}``.

    Produces ``(mantissa=scaled, exp=-scale_digits)``, i.e. the trivial
    representation that round-trips through :func:`decode_mantissa_exp`.

    Parameters
    ----------
    scaled : int
        Scaled-integer price.
    scale_digits : int
        Number of digits in the scale factor (default 4).

    Returns
    -------
    tuple[int, int]
        ``(mantissa, exponent)`` pair.
    """
    return scaled, -scale_digits
