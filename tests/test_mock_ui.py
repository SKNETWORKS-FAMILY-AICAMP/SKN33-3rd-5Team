"""Deterministic mock UI data tests that do not require model dependencies."""

from __future__ import annotations

import unittest
from pathlib import Path

from streamlit_app.mock_data import PRODUCTS, recommendation_conditions
from src.contracts import ConditionPayload


class MockUiDataTests(unittest.TestCase):
    def test_product_cards_have_local_images(self) -> None:
        self.assertEqual(len(PRODUCTS), 3)
        self.assertTrue(all(Path(product["image"]).is_file() for product in PRODUCTS))

    def test_recommendation_form_maps_explicit_values(self) -> None:
        conditions = recommendation_conditions(
            "카메라로 반려동물을 관찰하고 싶어요.",
            "입문자",
            "높음",
            True,
            True,
            False,
            True,
        )
        self.assertEqual(conditions["use_case"], "camera_monitoring")
        self.assertEqual(conditions["performance_priority"], "high")
        self.assertTrue(conditions["wireless_required"])
        self.assertTrue(conditions["camera_required"])
        self.assertFalse(conditions["gpio_required"])
        self.assertFalse(conditions["monitor_available"])
        # 화면의 JSON을 실제 추천 계약에 전달해도 버전 충돌이 없어야 한다.
        ConditionPayload.model_validate(conditions)

if __name__ == "__main__":
    unittest.main()
