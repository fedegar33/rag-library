"""The context picker reads public catalog metadata without running an agent."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from rag_library.main import app


class CatalogApiTests(unittest.TestCase):
    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.api.routes.list_books")
    def test_public_catalog_without_model_execution(self, catalog, agent):
        catalog.return_value = [
            {
                "id": 7,
                "title": "A book",
                "authors": None,
                "categories": [],
                "cover_url": None,
                "content_sha256": "private hash",
                "language": "en",
            }
        ]
        response = TestClient(app).get("/books")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "books": [
                    {
                        "id": 7,
                        "title": "A book",
                        "authors": None,
                        "categories": [],
                        "cover_url": None,
                    }
                ]
            },
        )
        agent.assert_not_called()

    @patch("rag_library.api.routes.list_books", return_value=[])
    def test_empty_catalog(self, catalog):
        self.assertEqual(TestClient(app).get("/books").json(), {"books": []})

    @patch("rag_library.api.routes.list_books", side_effect=RuntimeError("private"))
    def test_catalog_error_is_not_an_empty_library(self, catalog):
        response = TestClient(app).get("/books")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.text)
