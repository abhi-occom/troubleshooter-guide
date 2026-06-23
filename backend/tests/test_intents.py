from app.intents import (
    build_router_inventory_answer,
    build_structured_router_answer,
    is_router_inventory_question,
    router_name_from_filename,
)


def test_inventory_intent_examples():
    assert is_router_inventory_question("How many routers can we configure?")
    assert is_router_inventory_question("Which routers are available?")
    assert is_router_inventory_question("List the router names")
    assert not is_router_inventory_question("How do I reset HOME MESH PRO?")


def test_router_name_is_derived_from_filename():
    assert router_name_from_filename("HOME-MESH-PRO-setup.pdf") == "HOME MESH PRO"
    assert router_name_from_filename("Business_Router_X1_manual.pdf") == (
        "Business Router X1"
    )


def test_inventory_answer_ignores_documents_not_indexed():
    answer = build_router_inventory_answer(
        [
            {"filename": "router-one.pdf", "status": "indexed"},
            {"filename": "router-two.pdf", "status": "failed"},
        ]
    )

    assert "1 router setup guide is currently available" in answer
    assert "Router One" in answer
    assert "Router Two" not in answer


def test_structured_feature_and_comparison_answers_use_profiles():
    profiles = [
        {
            "filename": "mesh-pro.pdf",
            "router_name": "Mesh Pro",
            "model": "Wi-Fi 7",
            "supported_configuration": "Two mesh units",
            "features": ["Wi-Fi 7", "Mesh"],
            "topics": ["reset"],
        },
        {
            "filename": "basic.pdf",
            "router_name": "Basic Router",
            "model": "Wi-Fi 6",
            "supported_configuration": "One unit",
            "features": ["Wi-Fi 6"],
            "topics": [],
        },
    ]

    feature = build_structured_router_answer(
        "Which router supports Wi-Fi 7?", profiles
    )
    comparison = build_structured_router_answer("Compare the routers", profiles)

    assert "Mesh Pro" in feature
    assert "Basic Router" not in feature
    assert "Mesh Pro" in comparison
    assert "Basic Router" in comparison
