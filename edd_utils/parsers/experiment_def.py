from __future__ import unicode_literals
import collections
import json
import logging
import re

from jsonschema import Draft4Validator, FormatChecker
from builtins import (enumerate, float, len, object, range, super)
from django.core.exceptions import ValidationError

from main.models import MetadataType
from main.utilities import (NamingStrategy, CombinatorialDefinitionInput, AutomatedNamingStrategy)
from django.conf import settings

TYPICAL_ICE_PART_NUMBER_PATTERN = settings.TYPICAL_ICE_PART_NUMBER_PATTERN
LINE_NAME_COL_LABEL = 'Line Name'
LINE_DESCRIPTION_COL_REGEX = 'Line\s+Description'
STRAIN_IDS_COL_LABEL = 'Strains'
REPLICATE_COUNT_COL_REGEX = 'Replicate\s+Count'

_LINE_NAME_COL_PATTERN = re.compile(r'\s*%s\s*' % LINE_NAME_COL_LABEL, re.IGNORECASE)
_LINE_DESCRIPTION_COL_PATTERN = re.compile(r'\s*%s\s*' % LINE_DESCRIPTION_COL_REGEX, re.IGNORECASE)
_STRAIN_IDS_COL_PATTERN = re.compile(r'\s*%s\s*' % STRAIN_IDS_COL_LABEL, re.IGNORECASE)
_REPLICATE_COUNT_COL_PATTERN = re.compile(r'\s*%s\s*' % REPLICATE_COUNT_COL_REGEX)

_STRAIN_GROUPS_REGEX = r'\((:?\s*\d+\s*,?\s*)+\)'
_STRAIN_GROUPS_PATTERN = re.compile(_STRAIN_GROUPS_REGEX)

_TIME_VALUE_REGEX = r'^\s*(\d+(?:\.\d+)?)\s*h\s*$'
_TIME_VALUE_PATTERN = re.compile(_TIME_VALUE_REGEX, re.IGNORECASE)

# tests whether the input string ends with 's' or '(s)'
_PLURALIZED_REGEX = r'^%s(?:S|\(S\))$'

DUPLICATE_ASSAY_METADATA = 'duplicate_assay_metadata_cols'
DUPLICATE_LINE_METADATA = 'duplicate_line_metadata_cols'
SKIPPED_KEY = 'skipped_columns'

logger = logging.getLogger(__name__)


class _AssayMetadataValueParser(object):
    def parse(self, raw_value_str):
        """
        Parses the raw string input for a single assay metadata value
        :return the parsed value to store, or None if no value should be stored
        :raise ValueError if the value couldn't be parsed
        """
        pass


class _RawStringValueParser(_AssayMetadataValueParser):
    def parse(self, raw_value_str):
        stripped = raw_value_str.strip()
        if not stripped:
            return None
        return stripped


class _DecimalTimeParser(_AssayMetadataValueParser):
    def parse(self, raw_value_str):
        match = _TIME_VALUE_PATTERN.match(raw_value_str)
        if match:
            str_value = match.group(1)
            number_value = float(str_value)  # raises ValueError as in the spec
            stripped = str(str_value.strip()).replace(',', '').replace('-', '').replace('+', '')
            sep_index = stripped.find('.')  # TODO: i18n

            fractional_digits = 0
            if sep_index >= 0:
                fractional_digits = (len(stripped) - sep_index) - 1  # TODO: commas!
            print('time value "%s" has %d fractional digits' % (str_value, fractional_digits))
            return number_value, fractional_digits
        raise ValueError(
            """Value "%s" didn't match the expected time pattern (e.g. "4.0h")""" % raw_value_str)

# stateless value parsing strategies for metadata input (time is treated specially by the file
# format)
RAW_STRING_PARSER  = _RawStringValueParser()
TIME_PARSER = _DecimalTimeParser()


class ColumnLayout:
    """
    Stores column layout read from the header row of a template file. Since these files are
    designed to be user edited, parsing should be as tolerant as possible.
    """

    def __init__(self, errors, warnings):
        self.line_name_col = None
        self.line_description_col = None
        self.line_control_col = None
        self.replicate_count_col = None
        self.strain_ids_col = None
        self.col_index_to_line_meta_pk = {}
        self.col_index_to_assay_data = {}  # maps col index -> (Protocol, MetadataType)
        self.combinatorial_col_indices = []  # indices of all metadata columns for combinatorial
        self.unique_assay_protocols = {}
        self.errors = errors
        self.warnings = warnings

    def register_protocol(self, protocol):
        self.unique_assay_protocols[protocol.pk] = True

    def has_assay_metadata(self, upper_protocol_name, metadata_pk):
        """
        Tests whether any columns have been detected so far that store a specific (Protocol
        :param upper_protocol_name:
        :param metadata_pk:
        :return:
        """

        for col_index, (existing_protocol, existing_assay_meta_type) in \
                self.col_index_to_assay_data.items():
            if ((upper_protocol_name == existing_protocol.name.upper()) and (
                        metadata_pk == existing_assay_meta_type.pk)):
                return True
        return False

    def register_assay_meta_column(self, col_index, upper_protocol_name, protocol, assay_meta_type,
                                   is_combinatorial):

        # test for duplicate use of the same (Protocol, MetadataType) combination.
        # if we see it, log an error -- no clear/automated way for us to resolve which column
        #  has the correct values!
        if self.has_assay_metadata(upper_protocol_name, assay_meta_type.pk):
            dupes = self.errors.get(DUPLICATE_ASSAY_METADATA, [])
            if not dupes:
                self.errors[DUPLICATE_ASSAY_METADATA] = dupes
            dupes.append(assay_meta_type.pk)

        self.register_protocol(protocol)

        self.col_index_to_assay_data[col_index] = (protocol, assay_meta_type)
        if is_combinatorial:
            self.combinatorial_col_indices.append(col_index)

    def get_assay_metadata_type(self, col_index):
        value = self.col_index_to_assay_data.get(col_index, None)
        if not value:
            return None

        return value[1]

    @property
    def unique_protocols(self):
        return self.unique_assay_protocols.keys()

    def set_line_metadata_type(self, col_index, line_metadata_type, is_combinatorial=False):
        self.col_index_to_line_meta_pk[col_index] = line_metadata_type.pk


class _TemplateFileNamingStrategy(NamingStrategy):
    """
    A simple line/assay naming strategy assumed in the template file use case, where line names are
    user-specified and assay names are created automatically by appending the time to the line
    name. Note that this allows for duplicate assay names within different protocols,
    which should be clear in EDD's UI from protocol filtering and unit markings in the
    visualizations.
    """

    def __init__(self, assay_time_metadata_type_pk):
        super(_TemplateFileNamingStrategy, self).__init__()
        self.base_line_name = None
        self.assay_time_metadata_type_pk = assay_time_metadata_type_pk

    def get_line_name(self, strains, line_metadata, replicate_num, line_metadata_types, is_control):
        replicate_suffix = (('-R%d' % replicate_num)
                            if self.combinatorial_input.replicate_count > 1
                            else '')
        return '%(base_line_name)s%(replicate_suffix)s' % {
            'base_line_name': self.base_line_name, 'replicate_suffix': replicate_suffix,
        }

    def _get_time_format_string(self):
        if self.fractional_time_digits:
            return '%0.' + ('%d' % self.fractional_time_digits + 'f')
        return '%d'

    def get_assay_name(self, line, protocol, assay_metadata, assay_metadata_types):
        try:
            time_hours = assay_metadata.get(self.assay_time_metadata_type_pk)
            time_str = self._get_time_format_string() % time_hours
            return '%(line_name)s-%(hours)sh' % {
                'line_name': line.name, 'hours': time_str,
            }
        except KeyError:
            raise ValueError(KeyError)  # raise more generic Exception published in the docstring


# class _IncrementalNamingStrategy(NamingStrategy):
#     """
#     A simplistic naming strategy that creates line names by incrementing a counter each time
#     get_line_name() gets called.  This is a crutch for testing the basics of JSON-based
#     combinatorial line creation without the need to implement the planned / fully-configurable
#     line creation options in _AutomatedNamingStrategy.
#     """
#     def __init__(self, assay_time_metadata_type_pk):
#         super(_IncrementalNamingStrategy, self).__init__()
#         self.next_line_number = 1
#
#     def get_line_name(self, strains, line_metadata, replicate_num, line_metadata_types, is_control):
#         line_name = str(self.next_line_lumber)
#         self.next_line_number+=1
#         return line_name
#
#     def get_assay_name(self, line, protocol, assay_metadata, assay_metadata_types):
#         return line.name

class _InputFileRow(CombinatorialDefinitionInput):
    """
    A special case of combinatorial line/assay creations in support of template file
    upload. Each line of the template file is itself a combinatorial line/assay creation, at
    least if protocols/times are included, or the more advanced combinatorial features used.
    One-line-per-row creation, which is what users will likely use templates for most
    often, is just a degenerate case of combinatorial creation.
    """

    def __init__(self, assay_time_meta_pk):
        super(_InputFileRow, self).__init__(_TemplateFileNamingStrategy(assay_time_meta_pk))

    @property
    def base_line_name(self):
        return self.naming_strategy.base_line_name

    @base_line_name.setter
    def base_line_name(self, name):
        self.naming_strategy.base_line_name = name


class CombinatorialInputParser(object):
    def __init__(self, protocols, line_metadata_types_by_pk, assay_metadata_types_by_pk):

        # if the metadata type is present in the database, construct a parser for assay time
        # (we need a pk to store it, and the parser
        assay_time_type = None
        for pk, metadata_type in assay_metadata_types_by_pk.items():
            if metadata_type.type_name.upper() == 'TIME':
                assay_time_type = metadata_type
                break

        self.assay_time_metadata_type_pk = assay_time_type.pk

    def parse(self, input, errors, warnings):
        raise NotImplementedError()  # require subclasses to implement


class TemplateFileParser(CombinatorialInputParser):
    """
    File parser that takes a study "template file" as input and reads the contents into a list of
    CombinatorialCreationInput objects.
    """

    # initializer for TemplateFileParser
    def __init__(self, protocols_by_pk, line_metadata_types_by_pk, assay_metadata_types_by_pk,
                 require_strains=False):
        super(TemplateFileParser, self).__init__(protocols_by_pk, line_metadata_types_by_pk,
                                                 assay_metadata_types_by_pk)
        self.protocols_by_name = {protocol.name.upper(): protocol for protocol_pk, protocol in
                                  protocols_by_pk.items()}

        self.line_metadata_types_by_name = {meta.type_name.upper(): meta for pk, meta in
                                            line_metadata_types_by_pk.items()}

        self.assay_metadata_types_by_name = {meta.type_name.upper(): meta for pk, meta in
                                             assay_metadata_types_by_pk.items()}

        # print a warning for unlikely case-sensitivity-only metadata naming differences that
        # clash with
        # tolerant case-insensitive matching of user input in the file (which is a lot more
        # likely to be
        # inconsistent)
        if len(self.line_metadata_types_by_name) != len(line_metadata_types_by_pk):
            logger.warning(
                'Found some line metadata types that differ only by case. Case-insensitive '
                'matching in this function will arbitrarily choose one')

        if len(self.assay_metadata_types_by_name) != len(assay_metadata_types_by_pk):
            logger.warning(
                'Found some assay metadata types that differ only by case. Case-insensitive '
                'matching in this function will arbitrarily choose one')

        #TODO: also print a warning for protocols

        self.column_layout = None
        self.errors = []
        self.warnings = []

        # true to require that each line have at least one associated strain
        self.require_strains = require_strains

        # true to treat all unmatched column headers as an
        # error. False to ignore unmatch line headers, but to treat those that start with a
        # protocol name and don't match an assay MetaDataType as an error
        self.REQUIRE_COL_HEADER_MATCH = True

        # if the metadata type is present in the database, construct a parser for assay time
        # (we need a pk to store it, and the parser
        assay_time_type = self.assay_metadata_types_by_name.get('TIME', None)
        self.assay_time_metadata_type_pk = assay_time_type.pk if assay_time_type else None

        self.max_fractional_time_digits = 0

    def parse(self, wb, errors, warnings):

        # Clear out state from any previous use of this parser instance
        self.column_layout = None
        self.errors = errors
        self.warnings = warnings

        # loop over rows
        parsed_row_inputs = []
        for sheet_index, worksheet in enumerate(wb):

            # loop over columns
            for row_index, cols_list in enumerate(worksheet):

                # identify columns of interest first by looking for required labels
                if not self.column_layout:
                    self.column_layout = self.read_column_layout(cols_list)

                # if column labels have been identified, look for line creation input data
                else:
                    row_num = row_index + 1
                    row_inputs = self.read_template_row(cols_list, row_num)
                    if row_inputs:
                        parsed_row_inputs.append(row_inputs)

        for combinatorial_input in parsed_row_inputs:
            combinatorial_input.fractional_time_digits = self.max_fractional_time_digits

        return parsed_row_inputs

    def read_column_layout(self, row):
        """
        Detects the layout of a template file by matching cell contents of a row containing the
        minimal required column headers, then comparing additional headers in that row against line and
        assay metadata names in EDD's database. If required column headers aren't found in this row,
        the it's ignored. Columns can be provided in any order.
        :param row: the row to inspect for column headers
        :return: the column layout if required columns were found, or None otherwise
        """
        layout = ColumnLayout(self.errors, self.warnings)

        ###########################################################################################
        # loop over columns in the current row, looking for labels that identify at least the
        # minimum set of required columns
        ############################################################################################
        found_col_labels = False
        for col_index in range(len(row)):
            cell_content = row[col_index].value.strip()
            # skip this cell if the cell has no non-whitespace content
            if not cell_content:
                continue

            ########################################################################################
            # check whether column label matches one of the fixed labels specified by the file
            # format
            ########################################################################################
            if _LINE_NAME_COL_PATTERN.match(cell_content):
                layout.line_name_col = col_index
            elif _LINE_DESCRIPTION_COL_PATTERN.match(cell_content):
                layout.line_description_col = col_index
            elif _STRAIN_IDS_COL_PATTERN.match(cell_content):
                layout.strain_ids_col = col_index
            elif _REPLICATE_COUNT_COL_PATTERN.match(cell_content):
                layout.replicate_count_col = col_index
            # TODO: add support for control column

            # check whether the column label matches custom data defined in the database
            else:

                upper_content = cell_content.upper()

                # test whether this column is protocol-prefixed assay metadata
                assay_meta_type = self._parse_assay_metadata_header(layout, upper_content,
                                                                    col_index)

                # if we found the type of this column, proceed to the next
                if assay_meta_type:
                    continue

                # if this column isn't protocol-prefixed, test whether it's for line metadata
                line_metadata_type = self._parse_line_metadata_header(layout, upper_content,
                                                                      col_index,)

                # if we didn't process this column, track a warning that describes
                # dropped columns (can be displayed later in the UI)
                if line_metadata_type is None:
                    result_dest = self.errors if self.REQUIRE_COL_HEADER_MATCH else self.warnings
                    skipped_cols = result_dest.get(SKIPPED_KEY, [])
                    if not skipped_cols:
                        result_dest[SKIPPED_KEY] = skipped_cols
                    skipped_cols.append({
                        'col_index': col_index, 'title:': cell_content,
                    })

                # test whether we've located all the required columns
                found_col_labels = ((layout.line_name_col is not None) and
                                   ((not self.require_strains) or layout.strain_ids_col))

        # return the columns found in this row if at least the
        # minimum required columns were found
        if found_col_labels:
            return layout

        return None

    def _parse_assay_metadata_header(self, layout, upper_content, col_index):
        """
        :return: a truthy value if the content should be treated as assay metadata (the MetadataType
        if one was found, or True if it was clearly intended to be one, but was logged as an error).
        """

        ########################################################################################
        # loop over protocol names, testing for a protocol prefix in the column header
        ########################################################################################
        for upper_protocol_name, protocol in self.protocols_by_name.items():
            if upper_content.startswith(upper_protocol_name):

                # pull out the column header suffix following the protocol.
                # it should match the name of an assay metadata type
                assay_meta_suffix = upper_content[len(upper_protocol_name):].strip()

                suffix_meta_type = None
                is_combinatorial = False

                ################################################################################
                # loop over assay metadata types, testing for an assay metadata suffix in the
                # column header
                ################################################################################
                for assay_metadata_type in self.assay_metadata_types_by_name.values():

                    # look for an exact match
                    suffix_meta_type = self.assay_metadata_types_by_name .get(assay_meta_suffix,
                                                                             None)

                    if suffix_meta_type is not None:
                        layout = self.column_layout
                        layout.register_assay_meta_column(col_index, upper_protocol_name,
                                                          protocol, suffix_meta_type,
                                                          is_combinatorial)
                        break

                    # if no exact match is found look for a pluralized version of the metadata
                    # type name. Pluralization indicates the contents should be treated as a
                    # comma-delimited list of combinatorial metadata values
                    meta_regex = _PLURALIZED_REGEX % re.escape(assay_metadata_type.type_name)
                    pluralized_match = re.match(meta_regex, assay_meta_suffix, re.IGNORECASE)

                    if pluralized_match:
                        is_combinatorial = True
                        logger.debug('column header suffix %s matched pluralized regex %s' % (
                              assay_meta_suffix, meta_regex))
                        suffix_meta_type = assay_metadata_type
                        break
                    else:
                        logger.debug('column header suffix %s did not match pluralized regex %s' % (
                            assay_meta_suffix, meta_regex))

                # if the column started with the name of a protocol and ended with an
                # assay metadata type name, store the association of this column with the
                # (Protocol, MetadataType) combination
                if suffix_meta_type:
                    layout.register_assay_meta_column(col_index, upper_protocol_name,
                                                      protocol, suffix_meta_type,
                                                      is_combinatorial)
                    return suffix_meta_type

                # otherwise, since the column header was prefixed with a valid
                # protocol name, assume there was a data entry error or missing metadata type
                # in the database. This check is especially important for the Time metadata
                # assumed by the file format.
                else:
                    UNMATCHED_HEADERS_KEY = 'unmatched_column_header_indexes'
                    errors = self.errors
                    unmatched_cols = errors.get(UNMATCHED_HEADERS_KEY, [])
                    if not unmatched_cols:
                        errors[UNMATCHED_HEADERS_KEY] = unmatched_cols
                    unmatched_cols.append(col_index)
                    return True

    def _parse_line_metadata_header(self, column_layout, upper_content, col_index):
        """
        :return: the line MetadataType if one was found or None otherwise
        """

        line_metadata_types = self.line_metadata_types_by_name

        # test whether the cell content matches the name of a line metadata type
        line_metadata_type = line_metadata_types.get(upper_content, None)
        if line_metadata_type is not None:
            column_layout.set_line_metadata_type(col_index, line_metadata_type)
            return line_metadata_type

        # if we didn't find the singular form of the column header as line metadata, look
        # for a pluralized version that we'll treat as combinatorial line creation input
        for upper_metadata_type_name, meta_type in line_metadata_types.items():

            meta_regex = _PLURALIZED_REGEX % upper_metadata_type_name
            pluralized_match = re.match(meta_regex, upper_content)

            if pluralized_match:
                line_metadata_type = meta_type
                self.column_layout.set_line_metadata_type(col_index, line_metadata_type,
                                                          is_combinatorial=True)
                return line_metadata_type

        return None

    def read_template_row(self, cols_list, row_num):
        """
        Reads a single spreadsheet row to find line creation inputs. The row is read even if errors
        occur, logging errors in the 'errors' parameter so that multiple user input errors can be
        detected and communicated during a single pass of editing the file
        :param layout: the column header layout read from the beginning of the file. Informs this method
        which optional columns have been defined, as well as what order the columns are in (arbitrary
        column order is supported).
        :param line_metadata_types:
        :param cols_list:
        :param row_num:
        :param errors:
        :param warnings:
        :param REQUIRE_STRAINS:
        :return:
        """
        row_inputs = _InputFileRow(self.assay_time_metadata_type_pk)

        errors = self.errors
        layout = self.column_layout

        ###################################################
        # Line name
        ###################################################
        cell_content = cols_list[layout.line_name_col].value.strip()

        if cell_content:
            row_inputs.base_line_name = cell_content

        # otherwise, track error state, but keep going so we can try to detect all the
        # errors with a single pass
        else:
            logger.debug('Parse error: Cell in row %(row_num)d, column %(col)d was empty, '
                         'but was expected  to contain a name for the EDD line.' % {
                               'row_num': row_num, 'col': layout.line_name_col + 1,
                           })

            MISSING_LINE_NAME_ROWS_KEY = 'missing_line_name_rows'
            missing_row_nums = errors.get(MISSING_LINE_NAME_ROWS_KEY, None)
            if missing_row_nums is None:
                missing_row_nums = []
                errors[MISSING_LINE_NAME_ROWS_KEY] = missing_row_nums

        ###################################################
        # Line description
        ###################################################
        if layout.line_description_col is not None:
            cell_content = cols_list[layout.line_description_col].value.strip()
            if cell_content:
                row_inputs.description = cell_content

        ###################################################
        # Control
        ###################################################
        if layout.line_control_col is not None:
            cell_content = cols_list[layout.line_control_col].value.strip().upper()
            if cell_content:
                tokens = cell_content.split(',')
                if len(tokens) == 1:
                    tokens = cell_content

                values = []
                for token in tokens:
                    is_control = "TRUE" == token or "YES" == cell_content
                    values.append(is_control)
                row_inputs.is_control = values

        ###################################################
        # Replicate count
        ###################################################
        if layout.replicate_count_col is not None:
            cell_content = cols_list[layout.replicate_count_col].value
            try:
                row_inputs.replicate_count = int(cell_content)
            except ValueError:
                invalid_count = 'invalid_replicate_count'
                missing = errors.get(invalid_count, [])
                if not missing:
                    errors[invalid_count] = missing
                missing.append(cell_content)


        ###################################################
        # Strain part number(s)
        ###################################################
        # TODO: after some initial testing, consider adding custom group support for Carbon Source
        # similar to that for strains. Since some changes to Carbon Source / Media tracking are needed,
        # we will probably want to defer support for Carbon Sources for now.
        # TODO: after using the combinatorial strain creation code here for some testing of other parts
        # of the back end, consider removing it since it will result in creation of lines with
        # duplicate names
        if layout.strain_ids_col is not None:
            cell_content = cols_list[layout.strain_ids_col].value
            tokens = cell_content.split(',')
            if tokens:

                # build a list of strain ids for this input
                individual_strain_ids = []

                # loop over comma-delimited tokens included in the cell
                for token in tokens:
                    token = token.strip()

                    # if this token is a paren-enclosed list of part numbers, it's a
                    # combinatorial strain creation group rather than single strain to be included
                    # in the list. That means that each top-level comma-delimited entry in the list
                    # will result in creation of at least one line
                    strain_group_match = _STRAIN_GROUPS_PATTERN.match(token)

                    if strain_group_match:
                        strain_group = (strain_id.strip() for strain_id in strain_group_match
                            .group(1).split(';'))
                        row_inputs.combinatorial_strain_id_groups.append(strain_group)
                    else:
                        individual_strain_ids.append(token)

                    # test whether the strain's part number matched the expected pattern.
                    # we'll allow all input through to the ICE query later in case our pattern is
                    # dated, but this way we can provide a more helpful prompt for bad user input
                    part_number_match = TYPICAL_ICE_PART_NUMBER_PATTERN.match(token)

                    if not part_number_match:
                        PART_NUMBER_PATTERN_UNMATCHED_WARNING = 'part_number_pattern_unmatched'
                        warnings = self.warnings
                        unmatched_part_nums = warnings.get(PART_NUMBER_PATTERN_UNMATCHED_WARNING,
                                                           None)
                        if not unmatched_part_nums:
                            unmatched_part_nums = []
                            warnings.append(PART_NUMBER_PATTERN_UNMATCHED_WARNING,
                                            unmatched_part_nums)
                            logger.warning('Expected ICE part number(s) in template file row '
                                           '%(row_num)d, but "%(token)s" didn\'t match the '
                                           'expected pattern. This is either bad user input,'
                                           'or indicates that the pattern needs updating.' % {
                                               'row_num': row_num, 'token': token})
                        unmatched_part_nums.add(token)

                # resolve inconsistent user entries, if present. assumption is that if any strain
                # groups were provided, even individual strains listed separately (i.e. with no
                # enclosing parens) should be treated as 1-element combinatorial strain groups
                # TODO: need to resolve this at DB interaction time, since row order can dictate
                # results here
                if row_inputs.combinatorial_strain_id_groups and individual_strain_ids:
                    for strain_id in individual_strain_ids:
                        row_inputs.combinatorial_strain_id_groups.append((strain_id,))
                    individual_strain_ids = []
                elif individual_strain_ids:
                    row_inputs.combinatorial_strain_id_groups.append(individual_strain_ids)

            elif self.require_strains:
                MISSING_STRAINS_KEY = 'rows_missing_strains'
                missing = errors.get(MISSING_STRAINS_KEY, [])
                if not missing:
                    errors[MISSING_STRAINS_KEY] = missing

        ###################################################
        # line metadata
        ###################################################
        if layout.col_index_to_line_meta_pk:
            for col_index, line_metadata_pk in layout.col_index_to_line_meta_pk.items():
                cell_content = cols_list[col_index].value.strip()

                if col_index in layout.combinatorial_col_indices:
                    self._parse_combinatorial_input(row_inputs, cell_content, row_num,
                                               col_index, line_metadata_pk, 'incorrect_format')
                else:
                    row_inputs.add_common_line_metadata(line_metadata_pk, cell_content)

        ###################################################################################
        # loop over protocol-specific columns (most likely related assay measurement times)
        ###################################################################################
        if layout.col_index_to_assay_data:

            # loop over per-protocol assay metadata columns
            for col_index, (protocol, assay_metadata_type) in \
                    layout.col_index_to_assay_data.items():

                cell_content = cols_list[col_index].value.strip()

                # if this cell is in a column of for combinatorial input, add it to that list
                if col_index in layout.combinatorial_col_indices:
                    is_time = assay_metadata_type.pk == self.assay_time_metadata_type_pk

                    error_key = ('incorrect_time_format' if is_time else
                                 'combinatorial_parse_error')
                    parser = TIME_PARSER if is_time else RAW_STRING_PARSER

                    self._parse_combinatorial_input(row_inputs, cell_content, row_num, col_index,
                                                    assay_metadata_type.pk, error_key,
                                                    protocol, parser)

                else:
                    if row_inputs.has_assay_metadata_type(protocol.pk, assay_metadata_type.pk):
                        # TODO could improve this error content with a more complex data structure
                        self._append_to_nested_errors_list(
                                errors, 'duplicate_assay_matadata_columns', protocol.pk,
                                assay_metadata_type.pk, col_index)
                    row_inputs.add_common_assay_metadata(protocol.pk, assay_metadata_type.pk,
                                                         cell_content)

        return row_inputs

    def _parse_combinatorial_input(self, row_inputs, cell_content, row_num, col_index,
                                   metadata_type_pk, error_key, protocol=None,
                                   value_parser=RAW_STRING_PARSER):
        """
        Parses the value of a single cell that may / may not have comma-separated combinatorial
        content.
        :param row_inputs:
        :param cell_content:
        :param row_num:
        :param col_index:
        :param metadata_type_pk:
        :param error_key:
        :param protocol:
        :param value_parser:
        :return:
        """

        for token in cell_content.split(','):
            token = token.strip()
            try:

                if value_parser == TIME_PARSER:
                    (parsed_value, fractional_digit_count) = value_parser.parse(token)
                    self.max_fractional_time_digits = max(self.max_fractional_time_digits,
                                                          fractional_digit_count)
                else:
                    parsed_value = value_parser.parse(token)

                if protocol:
                    row_inputs.add_combinatorial_assay_metadata(protocol.pk, metadata_type_pk,
                                                                parsed_value)
                else:
                    row_inputs.add_combinatorial_line_metadata(protocol.pk, metadata_type_pk,
                                                               parsed_value)
            except ValueError:
                logger.warning('ValueError parsing token "%(token)s" from cell content "%(cell)s" '
                               'in row_num=%(row)d col_num='
                               '%(col)d' % {
                                    'token': token,
                                    'cell': cell_content,
                                    'row': row_num,
                                    'col': col_index+1, })
                self._append_to_errors_list(error_key, (row_num, col_index+1,))
                break

    def _append_to_errors_list(self, key, append_value):
        err_list = self.errors.get(key, [])
        if not err_list:
            self.errors[key] = err_list
            err_list.append(append_value)

    def _append_to_nested_errors_list(self, key1, key2, key3, append_value):
        dict = self.errors.get(key1, {})
        if not dict:
            self.errors[key1] = dict

        nested_dict = dict.get(key2, {})
        if not nested_dict:
            dict[key2] = nested_dict

        inner_list = nested_dict.get(key3, [])
        if not inner_list:
            nested_dict[key3] = inner_list
        inner_list.append(append_value)

PARSE_ERROR = 'parse_error'


class JsonInputParser(CombinatorialInputParser):
    """
    Parses / verifies JSON input for combinatorial line creation. Note that instances of this
    class maintain a cache of protocols and metadata types defined in the database, so the lifecycle
    of each instance should be short.
    """
    def __init__(self, protocols_by_pk, line_metadata_types_by_pk, assay_metadata_types_by_pk,
                 require_strains=False):
        super(JsonInputParser, self).__init__(protocols_by_pk, line_metadata_types_by_pk,
                                              assay_metadata_types_by_pk)
        self.protocols_by_pk = protocols_by_pk
        self.line_metadata_types_by_pk = line_metadata_types_by_pk
        self.assay_metadata_types_by_pk = assay_metadata_types_by_pk
        self.require_strains = require_strains
        self.max_fractional_time_digits = 0

    def parse(self, input, errors, warnings):

        combinatorial_inputs = []

        schema = {
            "$schema": "http://json-schema.org/draft-04/schema#",
            'id': 'http://www.jbei.org/schemas/informatics/edd/combinatorial_definition.json',
            'description': 'Defines a repsesentation for combinatioral line/assay creation by the EDD',
            # 'definitions': {
            #     'input': {
            #         'type': 'object',
                    'properties': {
                    #     'oneOf': [
                    # {
                        'base_name': {
                            'type': 'string',}, #},
                    # {
                    #     'name_elements': {
                    #         'type': 'object',
                    #         'properties': {
                    #             _AutomatedNamingStrategy.ELEMENTS: {
                    #                 'type': 'array', 'items': {
                    #                     'enum': str(auto_naming_strategy.valid_items),
                    #                 }
                    #             },
                    #             _AutomatedNamingStrategy.CUSTOM_ADDITIONS: {
                    #                     'type': 'array',
                    #                     'items': {
                    #                         'type': 'object',
                    #                         'properties': {
                    #                             'label': {
                    #                                 'type': 'string'},
                    #                             'value': {
                    #                                 'type': 'string'}}}},
                    #             _AutomatedNamingStrategy.ABBREVIATIONS: {
                    #                     'type': 'object',
                    #                     'additionalProperties': {  # element-related defs
                    #                         'type': 'object',
                    #                         'additionalProperties': {  # value -> abbreviation map
                    #                             'type': ['string', 'integer']
                    #                         },
                    #                     }
                    #             },
                    #
                    #         }, 'required': [_AutomatedNamingStrategy.ELEMENTS]},}],
                    # NOTE: 'description' as in our models is a reserved keyword for jsonschema
                    'desc': {
                        'type': 'string', },
                    'is_control': {
                        'type': 'array',
                        # TODO: implication is that this should work, but no specific examples found
                        #  yet that use 'boolean' for 'items'/using jsonschema library
                        #'items': 'boolean',

                        'uniqueItems': True,
                        'maxItems': 2, },
                    'combinatorial_strain_id_groups': {
                        'type': 'array',
                        'items': [{'$ref': '#/definitions/strain_id'},
                                  {'$ref': '#/definitions/strain_id_group'}]},
                    'replicate_count': {
                        'type': 'integer',
                        'minimum': 1, },
                    'common_line_metadata': {
                        'type': 'object',
                        'additionalProperties': {
                            'type': 'array',
                        }
                    },
                    'combinatorial_line_metadata': {
                        'type': 'object',
                        'additionalProperties': {
                            'type': 'array', }},
                    'protocol_to_assay_metadata': {
                         "$ref": "#/definitions/protocol_to_assay_metadata_map"
                     },
                    # 'protocol_to_combinatorial_metadata': {
                    #     "$ref": "#/definitions/protocol_to_assay_metadata_map"
                    # },
                    'contact': {
                        'type': 'string'},
                    'experimenter': {
                        'type': 'string'},
                    'carbon_source': {
                        'type': 'integer'},
#             'additionalProperties': False, #},  #

                # 'protocol_to_assay_metadata_map': {
                #     'type': 'object',
                #     'additionalProperties': {  # per-protocol dict
                #             'type': 'object',
                #             'additionalProperties': {  # metadata-specific values
                #                 'oneOf': [  # metadata values list (or single item)
                #                     {
                #                         'type': 'array', 'items': ['string', 'number'],
                #                     }, {
                #                         'type': ['string', 'number']
                #                     }]
                #             }
                #         },
                # },

            # },
            #     },
                    },
            'additionalProperties': False, # TODO: not being applied!!
            'definitions': {
                'strain_id': {
                    'type': ['integer', 'string'],
                },
                'strain_id_group': {
                    'type': 'array', 'items': {'$ref': '#/definitions/strain_id'},
                'line_metadata_map': {
                    'type': 'object',
                    'additionalProperties': {  # metadata-specific values
                        'oneOf': [  # metadata values list (or single item)
                            {
                                'type': 'array', 'items': ['string', 'number'],
                            }, {
                                'type': ['string', 'number']
                            }]
                    }
                },
            },
        },

            # 'oneOf': [
            #     {'$ref': '#/definitions/input'},
            #     {
            #         'type': 'array',
            #         'items': {'$ref': '#/definitions/input'},
            #
            #     }
            # ],

        }

        # try to validate the JSON input against the schema (essentially verifies formatting /
        # non-key datatypes only)
        # try:
        Draft4Validator.check_schema(schema)  # TODO: move to a unit test
        validator = Draft4Validator(schema)
        validator.validate(input)
        validation_errors = validator.iter_errors(input)
        for err in validation_errors:
            print(str(err))
            self.add_parse_error(errors, err.message, '.'.join(list(err.absolute_path)))
        # jsonschema.validate(parsed_json, schema)
        # except ValidationError as v_err:
        #     self.add_parse_error(errors, str(v_err))
        #     return None

        if errors:
            return None

        ############################################################################################
        # Once validated, parse the JSON string into a Python dict or list
        # if validation succeeded, extract the naming strategy from the JSON, then pass the rest
        # as parameters to CombinatorialDefinitionInput

        parsed_json = json.loads(input)

        max_decimal_digits = 0

        # tolerate either a sequence of CombinatorialDefinitionInputs or a single one
        if not isinstance(parsed_json, collections.Sequence):
            parsed_json = [parsed_json]

        for value in parsed_json:
            description = value.pop('desc', None)  # work around reserved 'description' keyword in
                                                   # JSON schema

            # convert string-based keys required by JSON into their numeric equivalents
            # TODO: consider casting values too
            common_line_metadata = _copy_to_numeric_keys(value.pop('common_line_metadata', {}))
            combinatorial_line_metadata = _copy_to_numeric_keys(
                    value.pop('combinatorial_line_metadata', {}))
            protocol_to_assay_metadata = _copy_to_numeric_keys(
                    value.pop('protocol_to_assay_metadata', {}))
            protocol_to_combinatorial_metadata = _copy_to_numeric_keys(
                    value.pop('protocol_to_combinatorial_metadata', {}))

            naming_strategy = None
            naming_elements = value.pop('name_elements', None)
            if naming_elements:
                naming_strategy = AutomatedNamingStrategy(self.line_metadata_types_by_pk,
                                                          self.assay_metadata_types_by_pk,
                                                          self.assay_time_metadata_type_pk)
                elements = _copy_to_numeric_elts(naming_elements['elements'])
                abbreviations = _copy_to_numeric_keys(naming_elements['abbreviations'])

                naming_strategy.elements = elements
                naming_strategy.abbreviations = abbreviations
                naming_strategy.verify_naming_elts(errors)
            else:
                base_name = value.pop('base_name')
                naming_strategy = template_naming_strategy = (
                    _TemplateFileNamingStrategy(self.assay_time_metadata_type_pk))
                naming_strategy.base_line_name = base_name

            try:
                # just pass the JSON as initializer arguments. Won't verify the internal
                # structure/expected data types, but for starters that's probably a safe bet
                combo_input = CombinatorialDefinitionInput(naming_strategy,
                                                           description=description,
                                                           common_line_metadata=common_line_metadata,
                                                           combinatorial_line_metadata=combinatorial_line_metadata,
                                                           protocol_to_assay_metadata=protocol_to_assay_metadata,
                                                           protocol_to_combinatorial_metadata=protocol_to_combinatorial_metadata,
                                                           **value)

                # inspect JSON input to find the maximum number of decimal digits in the user input
                if self.assay_time_metadata_type_pk:
                    for protocol, assay_metadata in protocol_to_assay_metadata.items():
                        time_values = assay_metadata.get(self.assay_time_metadata_type_pk, [])
                        for time_value in time_values:
                            str_value = str(time_value)
                            if str_value != str((int(float(time_value)))):
                                decimal_digits = len(str_value) - str_value.find('.') - 1
                                max_decimal_digits = max(max_decimal_digits, decimal_digits)

                naming_strategy.combinatorial_input = combo_input
                combinatorial_inputs.append(combo_input)
            except RuntimeError as rte:
                self.add_parse_error(errors, str(rte))

        # verify primary key inputs from the JSON are for the expected MetaDataType context,
        # and that they exist, since there's no runtime checking for this at database item
        # creation time when they get (necessarily) shoved into the hstore field. Note that this is
        # an non-ideal comparison of database fields cached in memory, but should be an acceptable
        # risk of having a stale cache of these values, which should be recently gathered and very
        # unlikely to be stale.

        for combo_input in combinatorial_inputs:
            combo_input.verify_pks(self.line_metadata_types_by_pk, self.assay_metadata_types_by_pk,
                                   self.protocols_by_pk, errors, INVALID_PROTOCOL_META_PK,
                                   INVALID_LINE_META_PK, INVALID_ASSAY_META_PK, PARSE_ERROR)

        # TODO: verify ICE strains are provided for every input if required
        # if self.require_strains:
        #     for combo_input in combinatorial_inputs:
        #         if not combo_input.combinatorial_strain_id_groups:
        #             add_parse_error(errors, 'strains required for all lines')
        #
        #         elif isinstance(combo_input.combinatorial_strain_id_groups, collections.Sequence):
        #             for strain_id_group in combo

        # consistently use decimal or integer time in assay names based on whether any fractional
        # input was provided
        for combo_input in combinatorial_inputs:
            combo_input.fractional_time_digits = max_decimal_digits

        return combinatorial_inputs

    def add_parse_error(self, errors, msg):
        errs = errors.get(PARSE_ERROR, [])
        if not errs:
            errors[PARSE_ERROR] = errs
        errs.append(msg)

def _copy_to_numeric_elts(input_list):
    converted_list = []
    for index, element in enumerate(input_list):
        try:
            int_value = int(element)
            converted_list.append(int_value)
        except ValueError:
            converted_list.append(element)

    return converted_list
def _copy_to_numeric_keys(input_dict):
    converted_dict = {}
    for key, value in input_dict.items():

        # if value is a nested dict, do the same work on it
        if isinstance(value, dict):
            value = _copy_to_numeric_keys(value)
        try:
            int_value = int(key)
            converted_dict[int_value] = value
        except ValueError:
            converted_dict[key] = value
    return converted_dict

INVALID_LINE_META_PK = 'invalid_line_metadata_pks'
INVALID_PROTOCOL_META_PK = 'invalid_protocol_pks'
INVALID_ASSAY_META_PK = 'invalid_assay_metadata_pks'

