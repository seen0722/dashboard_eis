import pytest
from src.portfolio.model.mask import mask_names

PROTECT = {"THORPE", "KILO10", "ABLE"}


@pytest.mark.parametrize("text,expected,n", [
    ("Contact Jiayu Ong(翁家瑜) for DVT", "Contact [name] for DVT", 1),
    ("BILLY_CHEN(陳澤明) owns BSP", "[name] owns BSP", 1),
    ("Kent0810\nDVT1 System", "[name]\nDVT1 System", 1),
    ("KENNY1_TSAI did BIOS pre-test", "[name] did BIOS pre-test", 1),
    ("THORPE_MB & THORPE_FPC layout", "THORPE_MB & THORPE_FPC layout", 0),
    ("THORPE_MAIN rework", "THORPE_MAIN rework", 0),
    ("LPDDR5X線路設計。DVT-7 FAI", "LPDDR5X線路設計。DVT-7 FAI", 0),
    ("USB_C PD intermittent", "USB_C PD intermittent", 0),
    ("", "", 0),
])
def test_mask(text, expected, n):
    assert mask_names(text, PROTECT) == (expected, n)
