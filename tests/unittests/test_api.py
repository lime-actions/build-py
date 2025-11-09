import pytest
from limepackage import _api

# ======================================================================
parametrize = pytest.mark.parametrize


# ======================================================================
class Test_insert_option:

    @parametrize(
        ('option', 'reference'),
        (
            ('option', {'option': {}}),
            ('option-sub', {'option': {'option-sub': {}}}),
        ),
    )
    def test_empty_tree(self, option: str, reference: _api.OptionTree) -> None:
        option_tree: _api.OptionTree = {}
        _api._insert_option(option_tree, option)
        assert option_tree == reference

    # ------------------------------------------------------------------
    @parametrize(
        ('option', 'reference'),
        (
            ('optionb', {'option': {}, 'optionb': {}}),
            ('option-sub', {'option': {'option-sub': {}}}),
        ),
    )
    def test_pre_filled_tree(
        self, option: str, reference: _api.OptionTree
    ) -> None:
        option_tree: _api.OptionTree = {'option': {}}
        _api._insert_option(option_tree, option)
        assert option_tree == reference


# ======================================================================
class Test_search_versions:

    def test_not_found(self):
        assert _api.search_versions('_') is None

    # ------------------------------------------------------------------
    def test_limedev(self):
        assert _api.search_versions('limedev') is not None


# ======================================================================
