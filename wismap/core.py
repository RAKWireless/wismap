"""
WisMAP core business logic — pure data in, data out.
No rich, no inquirer, no print. Suitable for CLI and API consumption.
"""

import os
import re
import copy

import yaml
from mergedeep import merge

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

PINS_PER_TYPE = {
    'Accessories': 0,
    'WisBase': 0,
    'WisCore': 40,
    'WisIO': 40,
    'WisModule': 0,
    'WisPower': 40,
    'WisSensor': 24,
}

SLOT_NAMES = {
    'BASE': 'Base board',
    'CORE': 'Core module',
    'SENSOR_A': 'SENSOR_A slot',
    'SENSOR_B': 'SENSOR_B slot',
    'SENSOR_C': 'SENSOR_C slot',
    'SENSOR_D': 'SENSOR_D slot',
    'SENSOR_E': 'SENSOR_E slot',
    'SENSOR_F': 'SENSOR_F slot',
    'IO_A': 'IO_A slot',
    'IO_B': 'IO_B slot',
    'POWER': 'Power slot',
}

SLOT_ORDER = ['CORE', 'POWER', 'IO_A', 'IO_B',
              'SENSOR_A', 'SENSOR_B', 'SENSOR_C', 'SENSOR_D',
              'SENSOR_E', 'SENSOR_F']

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _normalize_i2c_address(value):
    """Normalize i2c_address to a list or None."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]

# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------

def load_data(data_folder="./data"):
    definitions_file = os.path.join(data_folder, "definitions.yml")
    config_file = os.path.join(data_folder, "config.yml")
    rules_file = os.path.join(data_folder, "rules.yml")

    definitions = {}
    if os.path.isfile(definitions_file):
        with open(definitions_file) as f:
            definitions = yaml.load(f, Loader=yaml.loader.SafeLoader)
    definitions = dict(sorted(definitions.items(), key=lambda e: int(re.findall(r"\d+", e[0])[0])))

    config = {}
    if os.path.isfile(config_file):
        with open(config_file) as f:
            config = yaml.load(f, Loader=yaml.loader.SafeLoader)

    rules = []
    if os.path.isfile(rules_file):
        with open(rules_file) as f:
            rules_data = yaml.load(f, Loader=yaml.loader.SafeLoader)
            rules = rules_data.get('rules', []) if rules_data else []

    return definitions, config, rules


def load_data_v1(data_folder="./data"):
    """Same as load_data but also returns the precomputed compatible-slots index."""
    definitions, config, rules = load_data(data_folder)
    compatible_slots_index = _build_compatible_slots_index(definitions)
    return definitions, config, rules, compatible_slots_index

# -----------------------------------------------------------------------------
# Action: list
# -----------------------------------------------------------------------------

def list_modules(definitions, type_filter=None):
    result = []
    for module_id, module_data in definitions.items():
        if type_filter and module_data['type'] != type_filter:
            continue
        result.append({
            'id': module_id,
            'type': module_data['type'],
            'description': module_data['description'],
            'tags': module_data.get('tags', []),
        })
    return result

# -----------------------------------------------------------------------------
# Action: info
# -----------------------------------------------------------------------------

def get_module_info(definitions, config, module_id, show_nc=False):
    module_id = module_id.strip().lower()
    if module_id not in definitions:
        return None

    mod = definitions[module_id]
    notes = list(mod.get('notes', []))

    info = {
        'id': module_id,
        'type': mod['type'],
        'description': mod['description'],
        'documentation': mod.get('documentation', ''),
        'images': mod.get('images') or [],
        'schematics': mod.get('schematics') or [],
        'double': mod.get('double', False) if mod['type'] == 'WisSensor' else None,
        'i2c_address': _normalize_i2c_address(mod.get('i2c_address', None)),
        'tags': mod.get('tags', []),
        'mapping': None,
        'slots_table': None,
        'notes': None,
    }

    # Mapping table
    if 'mapping' in mod:
        pins = PINS_PER_TYPE.get(mod['type'], 0)
        mapping_rows = []
        if pins == 0:
            for k, v in mod['mapping'].items():
                if v:
                    mapping_rows.append({'pin': str(k), 'function': v})
        else:
            for index in range(pins):
                name = mod['mapping'].get(index + 1, 'NC')
                if name != 'NC' or show_nc:
                    mapping_rows.append({'pin': str(index + 1), 'function': name})
        info['mapping'] = mapping_rows

    # Slots table (for WisBase modules)
    if 'slots' in mod:
        slot_def = config.get('slots', {})
        slot_columns = list(mod['slots'].keys())

        for slot_name in slot_columns:
            slot_data = mod['slots'][slot_name] or {}
            double = slot_data.get('double', False)
            double_blocks = slot_data.get('double_blocks', None)
            if double_blocks:
                notes.append(f"Accepts long sensor on {slot_name} slot but blocking {double_blocks} slot")
            elif double:
                notes.append(f"Accepts long sensor on {slot_name} slot")

        # Resolve slots (deepcopy to avoid mutating config)
        resolved_slots = {}
        for slot_name in slot_columns:
            resolved_slots[slot_name] = merge(
                copy.deepcopy(slot_def[slot_name]),
                mod['slots'][slot_name] or {}
            )

        rows = []
        for i in range(1, 41):
            row = {'pin': str(i)}
            for slot_name in slot_columns:
                if i in resolved_slots[slot_name]:
                    val = resolved_slots[slot_name][i]
                    if val != "NC" or show_nc:
                        row[slot_name] = val
                    else:
                        row[slot_name] = ""
                else:
                    row[slot_name] = ""
            rows.append(row)

        info['slots_table'] = {
            'columns': slot_columns,
            'rows': rows,
        }

    info['notes'] = notes
    return info

# -----------------------------------------------------------------------------
# Action: combine — helpers
# -----------------------------------------------------------------------------

def _combine_pins(slot, mapping):
    output = {}
    for k, v in slot.items():
        if (v not in output) or (output[v] == ''):
            output[v] = mapping.get(k, "")
    return output


def _count_non_empty(elements):
    return sum(1 for e in elements if e != '' and '(NC)' not in e)


def _count_unique(elements):
    unique = []
    for e in elements:
        if e != '' and e not in unique:
            unique.append(e)
    return len(unique)


def _function_mapping(definitions, config, mapping_name, slot_module, slots):
    slot_mapping = {}
    for slot in slot_module:
        slot_mapping[slot] = {}
        module = slot_module[slot]
        if module and module != 'BLOCKED' and module != 'EMPTY':
            if definitions[module]['type'] in ['WisBase']:
                slot_mapping[slot] = definitions[module].get('naming', {})
            elif definitions[module]['type'] in ['WisCore', 'WisIO', 'WisSensor', 'WisPower']:
                slot_mapping[slot] = _combine_pins(slots[slot], definitions[module].get('mapping', {}))
            addr = _normalize_i2c_address(definitions[module].get('i2c_address', None))
            slot_mapping[slot]['I2C_ADDR'] = ', '.join(addr) if addr else ""

    functions = config.get('functions', {}).get(mapping_name, [])
    function_slot = {}
    for function in functions:
        row = [function]
        for slot in slot_mapping:
            row.append(slot_mapping[slot].get(function, ""))
        function_slot[function] = row

    return function_slot


def _check_condition(condition, values):
    non_empty = _count_non_empty(values)
    if condition == 'duplicates':
        # Expand comma-separated values (e.g. I2C addresses) and check
        # for individual collisions across slots
        all_items = []
        for v in values:
            if v == '' or '(NC)' in v:
                continue
            all_items.extend(item.strip() for item in v.split(','))
        unique_items = set(all_items)
        return len(all_items) > len(unique_items)
    elif condition == 'any_used':
        return non_empty > 0
    elif condition == 'multiple_used':
        return non_empty > 1
    return False


def _evaluate_rules_v2(definitions, slot_module, function_slot, rules, i2c_overrides=None):
    """Walk rules.yml, return structured List[Conflict].

    Each conflict has v1 fields plus `_legacy_highlights` (private) so the
    legacy adapter can preserve the existing combine() behavior.
    """
    structured = []

    mapping_name = definitions[slot_module['BASE']].get('functions', 'default')
    base_id = slot_module['BASE']

    skip_columns = 3
    if mapping_name == 'raspberry':
        skip_columns -= 1
    if 'POWER' in slot_module:
        skip_columns += 1

    # function_slot rows are [function_name, val_slot_0, val_slot_1, ...].
    # `skip_columns` skips the header + the first N slot values (BASE, CORE, ...).
    # The matching slice into slot_module.keys() is offset by 1 (no header).
    slot_names_all = list(slot_module.keys())[skip_columns - 1:]

    for rule in rules:
        exclude = rule.get('exclude', [])
        if base_id in exclude:
            continue

        match = rule['match']
        if 'function' in match:
            target_functions = [match['function']]
        elif 'function_prefix' in match:
            target_functions = [
                f for f in function_slot
                if any(f.startswith(p) for p in match['function_prefix'])
            ]
        else:
            continue

        condition = match['condition']

        for func in target_functions:
            if func not in function_slot:
                continue

            values_all = function_slot[func][skip_columns:]

            if exclude:
                pairs = [(v, s) for v, s in zip(values_all, slot_names_all)
                         if slot_module.get(s) not in exclude]
                values = [p[0] for p in pairs]
                slot_names_active = [p[1] for p in pairs]
            else:
                values = list(values_all)
                slot_names_active = list(slot_names_all)

            # I2C address override applies before the duplicates check.
            if func == 'I2C_ADDR' and i2c_overrides:
                values = [
                    _i2c_override_for_slot(slot_module.get(s), s, i2c_overrides) or v
                    for v, s in zip(values, slot_names_active)
                ]

            if not _check_condition(condition, values):
                continue

            if 'also_requires' in match:
                ref = match['also_requires']
                ref_func = ref['function']
                if ref_func not in function_slot:
                    continue
                ref_values = function_slot[ref_func][skip_columns:]
                if not _check_condition(ref['condition'], ref_values):
                    continue

            involves = []
            for v, s in zip(values, slot_names_active):
                if not v or '(NC)' in str(v):
                    continue
                mod = slot_module.get(s)
                if mod and mod not in ('EMPTY', 'BLOCKED'):
                    involves.append({'module': _to_display_id(mod), 'slot': s})

            code = rule.get('code', 'pin_contention')
            severity = rule.get('severity', 'error')
            context = {'function': func}
            if code == 'i2c_address_collision':
                from collections import Counter
                items = []
                for v in values:
                    if v and '(NC)' not in str(v):
                        items.extend(item.strip() for item in str(v).split(','))
                duplicates = sorted({a for a, c in Counter(items).items() if c > 1})
                if duplicates:
                    context['addresses'] = duplicates
                context['bus'] = 'I2C1'
            elif code == 'pin_contention':
                context['pin'] = func
            elif code == 'power_pin_conflict':
                context['pin'] = 'IO2'
                context['rail'] = '3V3_S'

            structured.append({
                'code': code,
                'message': rule['description'].format(function=func),
                'severity': severity,
                'involves': involves,
                'context': context,
                '_legacy_highlights': rule.get('highlights', [func]),
            })

    return structured


def _i2c_override_for_slot(module_id, slot_name, overrides):
    """Look up an i2c_address_override by `<MODULE>@<SLOT>` key. Returns None if no match."""
    if not module_id or module_id in ('EMPTY', 'BLOCKED'):
        return None
    if not isinstance(module_id, str):
        return None
    key = f'{_to_display_id(module_id)}@{slot_name}'
    return overrides.get(key)


def _strip_private(conflict):
    """Drop underscore-prefixed fields before JSON serialization."""
    return {k: v for k, v in conflict.items() if not k.startswith('_')}


def _detect_conflicts(definitions, slot_module, function_slot, rules):
    """Legacy shape adapter — returns (highlighted_functions, free_text_notes).

    Kept for the legacy combine() path until the frontend migrates in Phase 4.
    """
    structured = _evaluate_rules_v2(definitions, slot_module, function_slot, rules, None)
    functions = []
    notes = []
    for c in structured:
        notes.append(c['message'])
        for h in c.get('_legacy_highlights', []):
            if h and h not in functions:
                functions.append(h)
    return functions, notes

# -----------------------------------------------------------------------------
# Action: combine — slot introspection
# -----------------------------------------------------------------------------

def get_base_slots(definitions, config, base_id):
    base_id = base_id.strip().lower()
    if base_id not in definitions or definitions[base_id]['type'] != 'WisBase':
        return None

    base = definitions[base_id]
    slot_def = config.get('slots', {})
    result = {}

    sorted_slots = sorted(base['slots'].items(),
                          key=lambda x: SLOT_ORDER.index(x[0]) if x[0] in SLOT_ORDER else len(SLOT_ORDER))

    for slot_name, slot_overrides in sorted_slots:
        slot_overrides = slot_overrides or {}
        resolved = merge(copy.deepcopy(slot_def[slot_name]), copy.deepcopy(slot_overrides))
        double = slot_overrides.get('double', False)
        double_blocks = slot_overrides.get('double_blocks', None)

        # Determine accepted types
        if slot_name.startswith('CORE'):
            accepts_types = ['WisCore']
        elif slot_name.startswith('SENSOR'):
            accepts_types = ['WisSensor']
        elif slot_name.startswith('IO'):
            accepts_types = ['WisIO']
        elif slot_name.startswith('POWER'):
            accepts_types = ['WisPower']
        else:
            accepts_types = []

        # Build eligible modules
        eligible = []
        for mod_id, mod_data in definitions.items():
            if mod_data['type'] not in accepts_types:
                continue
            # For non-double slots, skip double-size sensor modules
            if not double and mod_data.get('double', False):
                continue
            eligible.append({
                'id': mod_id,
                'type': mod_data['type'],
                'description': mod_data['description'],
            })

        result[slot_name] = {
            'double': double,
            'double_blocks': double_blocks,
            'eligible_modules': eligible,
        }

    return result

# -----------------------------------------------------------------------------
# Action: combine — main
# -----------------------------------------------------------------------------

def combine(definitions, config, base_id, slot_assignments, rules=None):
    """
    Run the combine analysis.

    Args:
        definitions: module definitions dict
        config: config dict
        base_id: base board module id (e.g. "rak19007")
        slot_assignments: dict mapping slot name to module id or "EMPTY"/"BLOCKED"
            e.g. {"CORE": "rak4631", "SENSOR_A": "rak1901", "SENSOR_B": "EMPTY", ...}

    Returns:
        dict with slot_module, columns, function_table, conflicts, documentation, notes
    """
    base_id = base_id.strip().lower()
    if base_id not in definitions:
        return None
    slot_module = {'BASE': base_id}

    # Resolve slot pin definitions (deepcopy to avoid mutation)
    slot_def = config.get('slots', {})
    slots = {}
    sorted_slot_names = sorted(definitions[base_id]['slots'].keys(),
                               key=lambda x: SLOT_ORDER.index(x) if x in SLOT_ORDER else len(SLOT_ORDER))
    for slot_name in sorted_slot_names:
        slots[slot_name] = merge(
            copy.deepcopy(slot_def[slot_name]),
            definitions[base_id]['slots'][slot_name] or {}
        )

    # Fill in slot_module from assignments, defaulting to EMPTY
    for slot_name in slots:
        assigned = slot_assignments.get(slot_name, 'EMPTY')
        if assigned and assigned.strip().lower() not in ('empty', 'blocked'):
            canonical = assigned.strip().lower()
            if canonical not in definitions:
                slot_module[slot_name] = 'EMPTY'
            else:
                slot_module[slot_name] = canonical
        else:
            slot_module[slot_name] = 'EMPTY'

    # Build function mapping
    mapping_name = definitions[base_id].get('functions', 'default')
    function_slot = _function_mapping(definitions, config, mapping_name, slot_module, slots)

    # Detect conflicts
    conflict_functions, conflict_notes = _detect_conflicts(definitions, slot_module, function_slot, rules or [])

    # Gather notes & documentation
    documentation = []
    notes = []
    for k, v in slot_module.items():
        if v in definitions:
            documentation.append(f"{definitions[v]['description']}: {definitions[v]['documentation']}")
            for note in definitions[v].get('notes', []):
                notes.append(f"{v.upper()}: {note}")

    # Build columns
    columns = ["Function"]
    for k in slot_module:
        columns.append(SLOT_NAMES.get(k, k))

    return {
        'slot_module': slot_module,
        'columns': columns,
        'function_table': function_slot,
        'conflicts': {
            'functions': conflict_functions,
            'notes': conflict_notes,
        },
        'documentation': documentation,
        'notes': notes,
    }


# =============================================================================
# v1 API helpers
# =============================================================================

# Module types that map to specific slot prefixes (used for compatible_slots
# index computation — includes Cores since a Core "fits" in the CORE slot).
_TYPE_TO_SLOT_PREFIX = {
    'WisCore': 'CORE',
    'WisIO': 'IO_',
    'WisSensor': 'SENSOR_',
    'WisPower': 'POWER',
}

# Module types exposed via /api/v1/modules. Cores have their own endpoint;
# Bases have their own. WisModule covers externally-connected modules (OLED,
# joysticks, keypads) that don't slot in the standard way but are still part of
# the catalog. Accessories (cables) are included so the frontend can show the
# complete catalog from this single endpoint.
_MODULE_LISTING_TYPES = {'WisIO', 'WisSensor', 'WisPower', 'WisModule', 'Accessories'}

# Roles ignored when deriving signals / interfaces (power, ground, USB, NC, etc.).
_STRUCTURAL_ROLES = {
    'GND', '3V3', '3V3_S', '5V', 'VDD', 'VDD_NRF', 'VBAT', 'VBAT_NRF', 'VBAT_SX',
    'VIN', 'VBUS', 'USB+', 'USB-', 'USB_P', 'USB_N',
    'NC', 'RESET', 'BOOT0', 'SW1',
    'LED1', 'LED2', 'LED3',
    'CHRG', 'EN',
}

# Module-side role -> signal alias (used in module.signal_map).
_MODULE_ROLE_TO_SIGNAL = {
    'I2C_SDA': 'SDA',
    'I2C_SCL': 'SCL',
    'I2C1_SDA': 'SDA',
    'I2C1_SCL': 'SCL',
    'I2C2_SDA': 'SDA2',
    'I2C2_SCL': 'SCL2',
    'SPI_CS': 'CS',
    'SPI_CLK': 'SCK',
    'SPI_SCK': 'SCK',
    'SPI_NSS': 'CS',
    'SPI_MISO': 'MISO',
    'SPI_MOSI': 'MOSI',
    'UART_TX': 'TX',
    'UART_RX': 'RX',
    'UART0_TX': 'TX',
    'UART0_RX': 'RX',
    'UART1_TX': 'TX1',
    'UART1_RX': 'RX1',
}


def _to_display_id(canonical_id):
    """rak4631 -> RAK4631; rak5005-o -> RAK5005-O."""
    if canonical_id is None:
        return None
    return canonical_id.upper()


def _to_canonical_id(maybe_display):
    """Any-case input -> canonical lowercase."""
    if maybe_display is None:
        return None
    return maybe_display.strip().lower()


def _clean_role(role):
    """Strip `(NC)` markers and whitespace from a role string."""
    if not isinstance(role, str):
        return None
    r = role.strip()
    if not r or r == 'NC' or '(NC)' in r:
        return None
    return r


def _interesting_role(role):
    """True if the role is a signal a generator would care about."""
    r = _clean_role(role)
    if r is None:
        return False
    return r not in _STRUCTURAL_ROLES


def _role_to_bus_family(role):
    """Map role to bus family (I2C, SPI, UART, GPIO, analog, I2S, PDM) or None."""
    r = _clean_role(role)
    if r is None:
        return None
    R = r.upper()
    if 'I2C' in R:
        return 'I2C'
    if R.startswith('SPI'):
        return 'SPI'
    if R.startswith('UART') or R.startswith('TXD') or R.startswith('RXD'):
        return 'UART'
    if R.startswith('AIN') or R.startswith('ADC') or R.startswith('ANALOG'):
        return 'analog'
    if R.startswith('I2S'):
        return 'I2S'
    if R.startswith('PDM'):
        return 'PDM'
    if R.startswith('IO') or R.startswith('GPIO'):
        return 'GPIO'
    return None


def _role_to_bus_instance(role):
    """Map role to specific bus instance (I2C1, UART0, SPI1, GPIO, analog) or None."""
    r = _clean_role(role)
    if r is None:
        return None
    R = r.upper()
    m = re.match(r'^I2C(\d+)_', R)
    if m:
        return f'I2C{m.group(1)}'
    if R in ('I2C_SDA', 'I2C_SCL'):
        return 'I2C1'
    m = re.match(r'^UART(\d+)_', R)
    if m:
        return f'UART{m.group(1)}'
    m = re.match(r'^[TR]XD(\d+)$', R)
    if m:
        return f'UART{m.group(1)}'
    if R.startswith('SPI'):
        return 'SPI1'
    if R.startswith('IO') or R.startswith('GPIO'):
        return 'GPIO'
    if R.startswith('AIN') or R.startswith('ADC'):
        return 'analog'
    return None


# ----- Core derivations -----

def _derive_core_peripherals(core_def, core_slot_def):
    """Bus instances the Core exposes via the CORE slot, given its pin mapping."""
    mapping = core_def.get('mapping') or {}
    peripherals = set()
    for pin_num, role in core_slot_def.items():
        if not isinstance(pin_num, int):
            continue
        mcu = mapping.get(pin_num)
        if mcu is None or (isinstance(mcu, str) and ('(NC)' in mcu or mcu.strip() == '')):
            continue
        bus = _role_to_bus_instance(role)
        if bus and bus != 'GPIO':
            peripherals.add(bus)
    peripherals.add('GPIO')
    return sorted(peripherals)


def _derive_compatible_bases(definitions):
    """Bases that expose a CORE slot."""
    return sorted(
        _to_display_id(bid)
        for bid, b in definitions.items()
        if b.get('type') == 'WisBase' and 'CORE' in (b.get('slots') or {})
    )


# ----- Module derivations -----

def _module_mapping_values(module_def):
    """Yield non-empty role strings from a module's mapping."""
    m = module_def.get('mapping') or {}
    for v in m.values():
        cleaned = _clean_role(v)
        if cleaned is not None:
            yield cleaned


def _derive_module_interfaces(module_def):
    """Bus families this module uses (e.g. ['I2C', 'SPI'])."""
    families = set()
    for role in _module_mapping_values(module_def):
        fam = _role_to_bus_family(role)
        if fam:
            families.add(fam)
    ordered = ['I2C', 'SPI', 'UART', 'analog', 'I2S', 'PDM', 'GPIO']
    return [f for f in ordered if f in families]


def _derive_module_signal_map(module_def):
    """Map module signal aliases (SDA, SCL, CS, ...) to {role: <role>}."""
    seen = {}
    for role in _module_mapping_values(module_def):
        alias = _MODULE_ROLE_TO_SIGNAL.get(role)
        if alias and alias not in seen:
            seen[alias] = {'role': role}
    return seen


def _derive_module_core_requirements(module_def):
    """Numbered peripherals the module needs (WisBlock-default bus per family)."""
    fams = _derive_module_interfaces(module_def)
    mapped = []
    for f in fams:
        if f == 'I2C':
            mapped.append('I2C1')
        elif f == 'SPI':
            mapped.append('SPI1')
        elif f == 'UART':
            # Module doesn't know which UART; expose the family.
            mapped.append('UART')
        elif f in ('analog', 'I2S', 'PDM', 'GPIO'):
            mapped.append(f)
    return {'peripherals': mapped}


def _derive_module_power(module_def):
    """Detect 3V3_S rail / IO2 enable from the module's pin mapping."""
    roles = [str(v) for v in _module_mapping_values(module_def)]
    uses_3v3_s = any('3V3_S' in r for r in roles)
    return {
        'rail': '3V3_S' if uses_3v3_s else '3V3',
        'control_pin': 'IO2' if uses_3v3_s else None,
        'warmup_ms': None,
        'current_typical_uA': None,
        'current_peak_mA': None,
    }


# ----- Base derivations -----

def _resolved_slot_pin_map(base_def, slot_def):
    """Resolve each slot's pin map (config + base overrides). Returns {slot: {pin: role}}."""
    resolved = {}
    for slot_name, overrides in (base_def.get('slots') or {}).items():
        if slot_name not in slot_def:
            continue
        merged = merge(copy.deepcopy(slot_def[slot_name]), copy.deepcopy(overrides or {}))
        resolved[slot_name] = merged
    return resolved


def _derive_base_slot_pin_map(base_def, slot_def):
    """For each slot, return a dict of role -> role for interesting roles."""
    out = {}
    for slot_name, merged in _resolved_slot_pin_map(base_def, slot_def).items():
        signals = {}
        for pin_num, role in merged.items():
            if not isinstance(pin_num, int):
                continue
            cleaned = _clean_role(role)
            if cleaned is None or not _interesting_role(cleaned):
                continue
            if cleaned not in signals:
                signals[cleaned] = cleaned
        out[slot_name] = signals
    return out


def _derive_base_shared_buses(slot_pin_map):
    """Group slots by which bus instance they share."""
    bus_to_slots = {}
    for slot_name, signals in slot_pin_map.items():
        seen_buses = set()
        for role in signals:
            bus = _role_to_bus_instance(role)
            if bus and bus != 'GPIO' and bus != 'analog':
                seen_buses.add(bus)
        for bus in seen_buses:
            bus_to_slots.setdefault(bus, set()).add(slot_name)
    return [
        {'bus': bus, 'slots': sorted(slots)}
        for bus, slots in sorted(bus_to_slots.items())
    ]


# ----- Extension-field derivations (frontend convenience, non-breaking) -----

def _derive_pin_mapping(def_dict, show_nc=False):
    """Return [{pin, function}] sorted by pin number, skipping NC unless show_nc=True."""
    mapping = def_dict.get('mapping') or {}
    if not isinstance(mapping, dict):
        return []
    pins_per_type = PINS_PER_TYPE.get(def_dict.get('type'), 0)
    rows = []
    if pins_per_type == 0:
        # Modules without fixed pin counts (WisBase, WisModule) — show whatever's listed.
        for k, v in mapping.items():
            if v:
                rows.append({'pin': str(k), 'function': v})
    else:
        for index in range(pins_per_type):
            name = mapping.get(index + 1, 'NC')
            if name != 'NC' or show_nc:
                rows.append({'pin': str(index + 1), 'function': name})
    return rows


def _derive_base_pin_mapping_table(base_def, slot_def, show_nc=False):
    """Return {columns: [slot names], rows: [{pin, [slot]: function, ...}]} for a base."""
    slots = base_def.get('slots') or {}
    if not slots:
        return None
    slot_columns = list(slots.keys())
    resolved_slots = {}
    for slot_name in slot_columns:
        slot_overrides = slots[slot_name] or {}
        if slot_name not in slot_def:
            continue
        resolved_slots[slot_name] = merge(
            copy.deepcopy(slot_def[slot_name]),
            slot_overrides,
        )
    rows = []
    for i in range(1, 41):
        row = {'pin': str(i)}
        for slot_name in slot_columns:
            resolved = resolved_slots.get(slot_name, {})
            if i in resolved:
                val = resolved[i]
                row[slot_name] = '' if (val == 'NC' and not show_nc) else val
            else:
                row[slot_name] = ''
        rows.append(row)
    return {'columns': slot_columns, 'rows': rows}


def _derive_base_slot_info(base_def):
    """{SLOT_NAME: {double, double_blocks, accepts_type, layer}} for combine-tool dropdowns."""
    out = {}
    for slot_name, overrides in (base_def.get('slots') or {}).items():
        overrides = overrides or {}
        out[slot_name] = {
            'double': bool(overrides.get('double', False)),
            'double_blocks': overrides.get('double_blocks'),
            'accepts_type': _slot_expected_type(slot_name),
            'layer': overrides.get('layer', 'top'),
        }
    return out


def _derive_base_notes(base_def):
    """Combine static notes with dynamic 'Accepts long sensor on X' messages."""
    notes = list(base_def.get('notes') or [])
    for slot_name, overrides in (base_def.get('slots') or {}).items():
        overrides = overrides or {}
        if overrides.get('double_blocks'):
            notes.append(
                f"Accepts long sensor on {slot_name} slot but blocking "
                f"{overrides['double_blocks']} slot"
            )
        elif overrides.get('double'):
            notes.append(f"Accepts long sensor on {slot_name} slot")
    return notes


# ----- Compatible-slots index -----

def _build_compatible_slots_index(definitions):
    """Precompute {canonical_module_id: {display_base_id: [slot_names]}}.

    Called once at load time. Slot ids are WisMAP descriptive names (SENSOR_A, ...).
    Base ids in the inner dict are display form (RAK19007) for direct embedding
    in v1 responses.
    """
    index = {}
    bases = [(bid, b) for bid, b in definitions.items() if b.get('type') == 'WisBase']
    for mid, m in definitions.items():
        mtype = m.get('type')
        if mtype not in _TYPE_TO_SLOT_PREFIX:
            continue
        is_double = m.get('double', False) and mtype == 'WisSensor'
        per_base = {}
        for bid, b in bases:
            base_slots = b.get('slots') or {}
            eligible = []
            for slot_name, overrides in base_slots.items():
                overrides = overrides or {}
                if mtype == 'WisCore' and slot_name != 'CORE':
                    continue
                if mtype == 'WisPower' and not slot_name.startswith('POWER'):
                    continue
                if mtype == 'WisIO' and not slot_name.startswith('IO_'):
                    continue
                if mtype == 'WisSensor' and not slot_name.startswith('SENSOR_'):
                    continue
                if is_double and not overrides.get('double', False):
                    continue
                eligible.append(slot_name)
            if eligible:
                per_base[_to_display_id(bid)] = sorted(
                    eligible,
                    key=lambda x: SLOT_ORDER.index(x) if x in SLOT_ORDER else len(SLOT_ORDER)
                )
        index[mid] = per_base
    return index


# =============================================================================
# v1 entry points (called by api_v1 blueprint)
# =============================================================================

def get_cores(definitions, config):
    """List Cores, summary form."""
    core_slot = (config.get('slots') or {}).get('CORE', {})
    out = []
    for cid, c in definitions.items():
        if c.get('type') != 'WisCore':
            continue
        out.append({
            'id': _to_display_id(cid),
            'name': c.get('description', ''),
            'type': 'WisCore',
            'category': c.get('category'),
            'mcu': c.get('mcu'),
            'lora_chip': c.get('lora_chip'),
            'peripherals': _derive_core_peripherals(c, core_slot),
            'datasheet_url': c.get('documentation') or None,
            'tags': c.get('tags') or [],
        })
    return out


def get_core(definitions, config, core_id, show_nc=False):
    """Get a single Core, full detail. Returns None if not found."""
    cid = _to_canonical_id(core_id)
    if cid not in definitions or definitions[cid].get('type') != 'WisCore':
        return None
    c = definitions[cid]
    core_slot = (config.get('slots') or {}).get('CORE', {})
    return {
        'id': _to_display_id(cid),
        'name': c.get('description', ''),
        'mcu': c.get('mcu'),
        'lora_chip': c.get('lora_chip'),
        'peripherals': _derive_core_peripherals(c, core_slot),
        'lora_pins': c.get('lora_pins'),
        'power_pins': c.get('power_pins'),
        'compatible_bases': _derive_compatible_bases(definitions),
        'notes': c.get('notes') or [],
        'datasheet_url': c.get('documentation') or None,
        # Frontend extension fields (non-breaking — clients can ignore):
        'pin_mapping': _derive_pin_mapping(c, show_nc),
        'images': c.get('images') or [],
        'schematics': c.get('schematics') or [],
        'tags': c.get('tags') or [],
    }


def get_bases(definitions):
    """List Bases, summary form."""
    out = []
    for bid, b in definitions.items():
        if b.get('type') != 'WisBase':
            continue
        slots = list((b.get('slots') or {}).keys())
        slots.sort(key=lambda x: SLOT_ORDER.index(x) if x in SLOT_ORDER else len(SLOT_ORDER))
        out.append({
            'id': _to_display_id(bid),
            'name': b.get('description', ''),
            'type': 'WisBase',
            'category': b.get('category'),
            'form_factor': b.get('form_factor'),
            'slots': slots,
            'core_socket': b.get('core_socket'),
            'datasheet_url': b.get('documentation') or None,
            'tags': b.get('tags') or [],
        })
    return out


def get_base(definitions, config, base_id, show_nc=False):
    """Get a single Base, full detail. Returns None if not found."""
    bid = _to_canonical_id(base_id)
    if bid not in definitions or definitions[bid].get('type') != 'WisBase':
        return None
    b = definitions[bid]
    slot_def = config.get('slots') or {}
    slots = list((b.get('slots') or {}).keys())
    slots.sort(key=lambda x: SLOT_ORDER.index(x) if x in SLOT_ORDER else len(SLOT_ORDER))
    slot_pin_map = _derive_base_slot_pin_map(b, slot_def)
    return {
        'id': _to_display_id(bid),
        'name': b.get('description', ''),
        'form_factor': b.get('form_factor'),
        'slots': slots,
        'core_socket': b.get('core_socket'),
        'slot_pin_map': slot_pin_map,
        'shared_buses': _derive_base_shared_buses(slot_pin_map),
        'datasheet_url': b.get('documentation') or None,
        # Frontend extension fields (non-breaking):
        'slot_info': _derive_base_slot_info(b),
        'pin_mapping_table': _derive_base_pin_mapping_table(b, slot_def, show_nc),
        'notes': _derive_base_notes(b),
        'images': b.get('images') or [],
        'schematics': b.get('schematics') or [],
        'tags': b.get('tags') or [],
        'i2c_address': b.get('i2c_address'),
        'naming': b.get('naming') or {},
    }


def get_modules_v1(definitions, compatible_slots_index, *,
                   type=None, category=None, interface=None, compatible_with_core=None):
    """List modules (summary), with v1-spec filters."""
    out = []
    for mid, m in definitions.items():
        mtype = m.get('type')
        if mtype not in _MODULE_LISTING_TYPES:
            continue
        if type is not None and mtype != type:
            continue
        if category is not None and m.get('category') != category:
            continue
        interfaces = _derive_module_interfaces(m)
        if interface is not None and interface not in interfaces:
            continue
        if compatible_with_core is not None:
            ccid = _to_canonical_id(compatible_with_core)
            if ccid not in definitions or definitions[ccid].get('type') != 'WisCore':
                continue
        compat = compatible_slots_index.get(mid, {})
        out.append({
            'id': _to_display_id(mid),
            'name': m.get('description', ''),
            'chip': m.get('chip'),
            'type': mtype,
            'category': m.get('category'),
            'interfaces': interfaces,
            'i2c_addresses': _normalize_i2c_address(m.get('i2c_address')) or [],
            'compatible_slots': compat,
            'datasheet_url': m.get('documentation') or None,
            'tags': m.get('tags') or [],
            'double': m.get('double', False) if mtype == 'WisSensor' else False,
        })
    return out


def get_module_v1(definitions, compatible_slots_index, module_id, show_nc=False):
    """Get a single module, full detail. Returns None if not found."""
    mid = _to_canonical_id(module_id)
    if mid not in definitions:
        return None
    m = definitions[mid]
    if m.get('type') not in _MODULE_LISTING_TYPES:
        return None
    return {
        'id': _to_display_id(mid),
        'name': m.get('description', ''),
        'chip': m.get('chip'),
        'type': m.get('type'),
        'category': m.get('category'),
        'interfaces': _derive_module_interfaces(m),
        'i2c_addresses': _normalize_i2c_address(m.get('i2c_address')) or [],
        'i2c_alternate_addresses': m.get('i2c_alternate_addresses') or [],
        'signal_map': _derive_module_signal_map(m),
        'compatible_slots': compatible_slots_index.get(mid, {}),
        'core_requirements': _derive_module_core_requirements(m),
        'power': _derive_module_power(m),
        'electrical_notes': None,
        'datasheet_url': m.get('documentation') or None,
        'example_urls': m.get('example_urls') or [],
        'tags': m.get('tags') or [],
        'images': m.get('images') or [],
        'schematics': m.get('schematics') or [],
        # Frontend extension fields (non-breaking):
        'pin_mapping': _derive_pin_mapping(m, show_nc),
        'double': m.get('double', False) if m.get('type') == 'WisSensor' else None,
        'notes': m.get('notes') or [],
    }


# =============================================================================
# v1 validate — resolve + structured conflicts
# =============================================================================

def _build_core_role_to_mcu_pin(core_def, core_slot_def):
    """Map each role assigned in the CORE slot to the Core's MCU pin at that pin number."""
    mapping = core_def.get('mapping') or {}
    out = {}
    for pin_num, role in core_slot_def.items():
        if not isinstance(pin_num, int):
            continue
        clean = _clean_role(role)
        if clean is None:
            continue
        mcu = mapping.get(pin_num)
        if isinstance(mcu, str) and mcu.strip() and '(NC)' not in mcu:
            if clean not in out:
                out[clean] = mcu.strip()
    return out


def _resolve_module_pins(module_def, slot_pin_resolved, core_role_to_mcu_pin):
    """For one module placed in one slot: signal_alias -> {role, wisblock_pin, mcu_pin}."""
    module_mapping = module_def.get('mapping') or {}
    pins = {}
    for pin_num, module_role in module_mapping.items():
        if not isinstance(pin_num, int):
            continue
        clean_mod_role = _clean_role(module_role)
        if clean_mod_role is None or not _interesting_role(clean_mod_role):
            continue
        alias = _MODULE_ROLE_TO_SIGNAL.get(clean_mod_role)
        if not alias:
            continue
        slot_role = _clean_role(slot_pin_resolved.get(pin_num))
        if slot_role is None:
            continue
        pins[alias] = {
            'role': slot_role,
            'wisblock_pin': f'WB_{slot_role}',
            'mcu_pin': core_role_to_mcu_pin.get(slot_role),
        }
    return pins


def _resolve_buses(slot_module, slot_pin_resolved, resolved_slots):
    """Group occupied slots by bus instance; attach I2C device records."""
    buses = {}
    for slot_name, pin_map in slot_pin_resolved.items():
        module_id = slot_module.get(slot_name)
        if not module_id or module_id in ('EMPTY', 'BLOCKED'):
            continue
        if isinstance(module_id, str) and module_id.startswith('UNKNOWN:'):
            continue
        seen = set()
        for pin_num, role in pin_map.items():
            if not isinstance(pin_num, int):
                continue
            bus = _role_to_bus_instance(_clean_role(role))
            if bus and bus not in ('GPIO', 'analog'):
                seen.add(bus)
        for bus in seen:
            entry = buses.setdefault(bus, {'slots': set(), 'devices': []})
            entry['slots'].add(slot_name)

    for slot_name, info in resolved_slots.items():
        if not info.get('i2c_address'):
            continue
        pin_map = slot_pin_resolved.get(slot_name, {})
        i2c_bus = None
        for pin_num, role in pin_map.items():
            bus = _role_to_bus_instance(_clean_role(role))
            if bus and bus.startswith('I2C'):
                i2c_bus = bus
                break
        if i2c_bus and i2c_bus in buses:
            buses[i2c_bus]['devices'].append({
                'module': info['module'],
                'slot': slot_name,
                'address': info['i2c_address'],
            })

    return {
        bus: {'slots': sorted(b['slots']), 'devices': b['devices']}
        for bus, b in sorted(buses.items())
    }


def _resolve_lorawan(core_def):
    if not core_def.get('lora_chip'):
        return None
    return {
        'chip': core_def.get('lora_chip'),
        'spi': 'SPI1',
        'pins': core_def.get('lora_pins'),
    }


def _slot_expected_type(slot_name):
    """Which module type a slot accepts."""
    if slot_name == 'CORE':
        return 'WisCore'
    if slot_name.startswith('IO_'):
        return 'WisIO'
    if slot_name.startswith('SENSOR_'):
        return 'WisSensor'
    if slot_name.startswith('POWER'):
        return 'WisPower'
    return None


def resolve(definitions, config, rules, core_id, base_id, slot_assignments,
            i2c_overrides=None):
    """Build the v1 ValidateResponse for a given configuration.

    Returns (response_dict, error_code, http_status):
      - response_dict: v1 shape `{valid, conflicts, warnings, resolved}` (or None on hard error)
      - error_code: 'core_not_found' | 'base_not_found' | None
      - http_status: 200 on success, 404 on hard error
    """
    base_canon = _to_canonical_id(base_id)
    if not base_canon or base_canon not in definitions or \
            definitions[base_canon].get('type') != 'WisBase':
        return None, 'base_not_found', 404

    base_def = definitions[base_canon]
    base_slots = base_def.get('slots') or {}
    base_has_core_slot = 'CORE' in base_slots

    core_canon = _to_canonical_id(core_id) if core_id else None
    if base_has_core_slot:
        if not core_canon or core_canon not in definitions or \
                definitions[core_canon].get('type') != 'WisCore':
            return None, 'core_not_found', 404
    else:
        # Coreless base (e.g. RAK6421 Pi Hat) — the host platform is the Core.
        core_canon = None

    core_def = definitions[core_canon] if core_canon else None
    slot_def_all = config.get('slots') or {}
    core_slot_def = slot_def_all.get('CORE', {})

    sorted_slot_names = sorted(
        base_slots.keys(),
        key=lambda x: SLOT_ORDER.index(x) if x in SLOT_ORDER else len(SLOT_ORDER)
    )

    # Build slot_module dict; CORE is injected from top-level `core` when present.
    slot_module = {'BASE': base_canon}
    if core_canon:
        slot_module['CORE'] = core_canon
    structured_runtime = []  # slot_incompatibility / unknown_module conflicts

    for slot_name in sorted_slot_names:
        if slot_name == 'CORE':
            continue
        assigned_raw = slot_assignments.get(slot_name, 'EMPTY')
        if not assigned_raw or str(assigned_raw).strip().lower() in ('empty', 'blocked'):
            slot_module[slot_name] = 'EMPTY'
            continue
        canon = _to_canonical_id(assigned_raw)
        if canon not in definitions:
            structured_runtime.append({
                'code': 'unknown_module',
                'message': f"Module '{assigned_raw}' is not known to WisMAP.",
                'severity': 'error',
                'involves': [{'module': str(assigned_raw), 'slot': slot_name}],
                'context': {'slot': slot_name},
            })
            slot_module[slot_name] = 'EMPTY'
            continue
        # Type compatibility check
        expected = _slot_expected_type(slot_name)
        actual = definitions[canon].get('type')
        if expected and actual != expected:
            structured_runtime.append({
                'code': 'slot_incompatibility',
                'message': (f"Module {_to_display_id(canon)} ({actual}) cannot fit "
                            f"slot {slot_name} (accepts {expected})."),
                'severity': 'error',
                'involves': [{'module': _to_display_id(canon), 'slot': slot_name}],
                'context': {'slot': slot_name, 'expected_type': expected, 'actual_type': actual},
            })
            slot_module[slot_name] = 'EMPTY'  # skip in resolved view
            continue
        slot_module[slot_name] = canon

    # Resolve every slot's pin map (config + base overrides).
    slot_pin_resolved = {}
    for slot_name in sorted_slot_names:
        if slot_name not in slot_def_all:
            continue
        overrides = base_slots.get(slot_name) or {}
        slot_pin_resolved[slot_name] = merge(
            copy.deepcopy(slot_def_all[slot_name]),
            copy.deepcopy(overrides),
        )

    core_role_to_mcu_pin = (
        _build_core_role_to_mcu_pin(core_def, core_slot_def) if core_def else {}
    )

    # Build resolved.slots
    resolved_slots = {}
    for slot_name in sorted_slot_names:
        if slot_name == 'CORE':
            continue
        module_id = slot_module.get(slot_name)
        if not module_id or module_id in ('EMPTY', 'BLOCKED'):
            continue
        module_def = definitions[module_id]
        addrs = _normalize_i2c_address(module_def.get('i2c_address')) or []
        i2c_address = addrs[0] if addrs else None
        override = _i2c_override_for_slot(module_id, slot_name, i2c_overrides or {})
        if override:
            i2c_address = override
        resolved_slots[slot_name] = {
            'module': _to_display_id(module_id),
            'i2c_address': i2c_address,
            'pins': _resolve_module_pins(
                module_def,
                slot_pin_resolved.get(slot_name, {}),
                core_role_to_mcu_pin,
            ),
            'power': _derive_module_power(module_def),
        }

    buses = _resolve_buses(slot_module, slot_pin_resolved, resolved_slots)
    lorawan = _resolve_lorawan(core_def) if core_def else None

    # Rule-driven conflicts (re-use the legacy data flow)
    mapping_name = base_def.get('functions', 'default')
    function_slot = _function_mapping(
        definitions, config, mapping_name, slot_module, slot_pin_resolved
    )
    rule_conflicts = _evaluate_rules_v2(
        definitions, slot_module, function_slot, rules, i2c_overrides
    )

    all_conflicts = structured_runtime + rule_conflicts
    errors = [c for c in all_conflicts if c.get('severity') == 'error']
    warnings = [c for c in all_conflicts if c.get('severity') == 'warning']
    valid = len(errors) == 0

    resolved_block = None
    if valid:
        resolved_block = {
            'core': _to_display_id(core_canon) if core_canon else None,
            'base': _to_display_id(base_canon),
            'slots': resolved_slots,
            'buses': buses,
            'lorawan': lorawan,
        }

    # Frontend extension data — the legacy combine() output shape.
    # The consumer contract ignores these fields per §2 forwards-compat.
    columns = ['Function']
    for k in slot_module:
        columns.append(SLOT_NAMES.get(k, k))
    documentation = []
    legacy_notes = []
    for k, v in slot_module.items():
        if v in definitions:
            documentation.append(
                f"{definitions[v]['description']}: {definitions[v]['documentation']}"
            )
            for note in definitions[v].get('notes', []):
                legacy_notes.append(f"{v.upper()}: {note}")
    highlighted = []
    for c in errors + warnings:
        for h in c.get('_legacy_highlights', []):
            if h and h not in highlighted:
                highlighted.append(h)

    return {
        'valid': valid,
        'conflicts': [_strip_private(c) for c in errors],
        'warnings': [_strip_private(c) for c in warnings],
        'resolved': resolved_block,
        # Frontend extension fields (non-breaking — clients can ignore):
        'function_table': function_slot,
        'columns': columns,
        'slot_module': {k: (_to_display_id(v) if v in definitions else v)
                        for k, v in slot_module.items()},
        'highlighted_functions': highlighted,
        'documentation': documentation,
        'notes': legacy_notes,
    }, None, 200


def _resolve_core_base(definitions, core, base):
    """Resolve + validate the (core, base) pair shared by validate_v1 and solve_v1.

    Returns (base_canon, core_canon, base_has_core, err):
      - base_canon:    canonical base id (None on error)
      - core_canon:    canonical core id, or None for coreless bases
      - base_has_core: whether the base exposes a CORE slot
      - err:           None, or a (code, message, http_status) tuple

    Centralising this keeps the 400 (core required) / 404 (unknown core/base) /
    coreless behaviour identical across both endpoints (spec 010 RQ-02).
    """
    base_canon = _to_canonical_id(base)
    base_def = definitions.get(base_canon)
    if not base_def or base_def.get('type') != 'WisBase':
        return None, None, False, (
            'base_not_found', f"Base '{base}' is not known to WisMAP.", 404)

    base_has_core = 'CORE' in (base_def.get('slots') or {})
    if base_has_core:
        if not isinstance(core, str) or not core:
            return base_canon, None, True, (
                'invalid_request', "Field `core` is required for this base.", 400)
        core_canon = _to_canonical_id(core)
        core_def = definitions.get(core_canon)
        if not core_def or core_def.get('type') != 'WisCore':
            return base_canon, None, True, (
                'core_not_found', f"Core '{core}' is not known to WisMAP.", 404)
        return base_canon, core_canon, True, None

    # Coreless base (e.g. RAK6421 Pi Hat): the host platform plays the Core role.
    if core is not None and (not isinstance(core, str) or not core):
        return base_canon, None, False, (
            'invalid_request', "Field `core` must be a string when provided.", 400)
    return base_canon, None, False, None


# ---------------------------------------------------------------------------
# Request-size guards (security 012) — bound attacker-controlled input before any
# expensive per-request work. Calibrated above the largest legitimate request
# (largest base = 10 slots); see ai/specs/012-security-assessment/.
# ---------------------------------------------------------------------------
MAX_MODULES = 24        # /solve modules[]  (~2x max slot count; preserves best-partial)
MAX_SLOTS = 12          # /validate slots[] (10 slots + CORE + margin)
MAX_I2C_OVERRIDES = 12  # options.i2c_address_overrides entries (one-per-slot ceiling)


def _extract_i2c_overrides(options):
    """Return (overrides_or_None, err) for `options.i2c_address_overrides`.

    Absent or null → (None, None). When present it must be an object with at most
    MAX_I2C_OVERRIDES entries; a non-object or oversized value yields an
    ('invalid_request', message) err tuple. (security 012 RQ-03)
    """
    if not isinstance(options, dict):
        return None, None
    overrides = options.get('i2c_address_overrides')
    if overrides is None:
        return None, None
    if not isinstance(overrides, dict):
        return None, ('invalid_request',
                      "`options.i2c_address_overrides` must be an object.")
    if len(overrides) > MAX_I2C_OVERRIDES:
        return None, ('invalid_request',
                      f"`options.i2c_address_overrides` exceeds the maximum of "
                      f"{MAX_I2C_OVERRIDES} entries.")
    return overrides, None


def validate_v1(definitions, config, rules, request_body):
    """Validate a `{core, base, slots, options}` request body.

    Returns (response_dict, error_code, http_status):
      - 200: response_dict is the v1 ValidateResponse; error_code is None.
      - 400: malformed JSON shape.
      - 404: unknown core or base.
      - 422: duplicate slot, or CORE entry in slots[] that disagrees with top-level core.
    """
    if not isinstance(request_body, dict):
        return None, ('invalid_request', "Request body must be a JSON object."), 400

    core = request_body.get('core')
    base = request_body.get('base')
    slots = request_body.get('slots')
    options = request_body.get('options') or {}

    if not isinstance(base, str) or not base:
        return None, ('invalid_request', "Field `base` is required."), 400
    if not isinstance(slots, list):
        return None, ('invalid_request', "Field `slots` must be an array."), 400
    if len(slots) > MAX_SLOTS:
        return None, ('invalid_request',
                      f"`slots` exceeds the maximum of {MAX_SLOTS} entries."), 400

    # `core` is required when the base exposes a CORE slot, optional otherwise.
    # Resolve via the shared helper so 400/404/coreless behaviour stays identical
    # to solve_v1 (spec 010 RQ-02).
    _base_canon, _core_canon, base_has_core, cb_err = _resolve_core_base(
        definitions, core, base)
    if cb_err is not None:
        code, message, status = cb_err
        return None, (code, message), status

    # Normalize slot entries and enforce uniqueness.
    slot_assignments = {}
    core_entries = []
    for i, entry in enumerate(slots):
        if not isinstance(entry, dict):
            return None, ('invalid_request', f"slots[{i}] must be an object."), 400
        slot_name = entry.get('slot')
        module_id = entry.get('module')
        if not isinstance(slot_name, str) or not slot_name:
            return None, ('invalid_request', f"slots[{i}].slot is required."), 400
        if not isinstance(module_id, str) or not module_id:
            return None, ('invalid_request', f"slots[{i}].module is required."), 400
        if slot_name == 'CORE':
            core_entries.append(module_id)
            continue
        if slot_name in slot_assignments:
            return None, ('duplicate_slot', f"Slot '{slot_name}' appears more than once."), 422
        slot_assignments[slot_name] = module_id

    # §3.5: CORE entry in slots[] tolerated only if it matches top-level `core`.
    if len(core_entries) > 1:
        return None, ('duplicate_slot', "CORE appears more than once in slots[]."), 422
    if core_entries:
        if not base_has_core:
            return None, (
                'duplicate_slot',
                f"Base {base} does not expose a CORE slot; remove the CORE entry "
                f"from slots[]."
            ), 422
        top_canon = _to_canonical_id(core)
        slot_canon = _to_canonical_id(core_entries[0])
        if top_canon != slot_canon:
            return None, (
                'duplicate_slot',
                f"CORE entry in slots[] ({core_entries[0]}) disagrees with top-level "
                f"core ({core}). Use the top-level `core` field only."
            ), 422

    i2c_overrides, ov_err = _extract_i2c_overrides(options)
    if ov_err is not None:
        return None, ov_err, 400

    response, err, status = resolve(
        definitions, config, rules, core, base, slot_assignments, i2c_overrides
    )
    if err is not None:
        return None, (err, _err_message(err, core, base)), status
    return response, None, 200


def _err_message(code, core, base):
    if code == 'core_not_found':
        return f"Core '{core}' is not known to WisMAP."
    if code == 'base_not_found':
        return f"Base '{base}' is not known to WisMAP."
    return code


# =============================================================================
# Slot solver (spec 010) — solve_v1 + helpers
# =============================================================================

_SOLVE_NODE_CAP = 10000  # backstop on explored branch-and-bound nodes


def _slot_layer(base_def, slot_name):
    """Physical face of a slot: 'top' (default) or 'bottom'."""
    return ((base_def.get('slots') or {}).get(slot_name) or {}).get('layer', 'top')


def _slot_sort_index(slot_name):
    return SLOT_ORDER.index(slot_name) if slot_name in SLOT_ORDER else len(SLOT_ORDER)


def _enumerate_assignments(candidates, base_def, cap=_SOLVE_NODE_CAP):
    """Branch-and-bound: find every maximum-cardinality module->slot assignment.

    `candidates` is a list of dicts with keys `eligible` (list of slot names) and
    `is_double` (bool). Returns `(assignments, truncated)` where each assignment is
    a dict `{slot_name: candidate_index}` and all share the maximum placement
    count M. Honours double/double_blocks: a double sensor consumes the blocked
    sibling slot. The node cap is a backstop for pathological input; when hit,
    `truncated` is True and M may not be the true maximum.
    """
    base_slots = base_def.get('slots') or {}
    n = len(candidates)
    state = {'M': 0, 'assigns': []}
    nodes = [0]
    truncated = [False]

    def upper_remaining(i, occupied):
        # Optimistic (admissible) count of candidates[i:] that still have a free
        # eligible slot — ignores contention, so it never under-counts.
        cnt = 0
        for j in range(i, n):
            if any(s not in occupied for s in candidates[j]['eligible']):
                cnt += 1
        return cnt

    def recurse(i, placed, assign, occupied):
        if truncated[0]:
            return
        if nodes[0] >= cap:
            truncated[0] = True
            return
        nodes[0] += 1

        if i == n:
            if placed > state['M']:
                state['M'] = placed
                state['assigns'] = [dict(assign)]
            elif placed == state['M'] and placed > 0:
                state['assigns'].append(dict(assign))
            return

        # Prune branches that cannot match the best placement found so far.
        if placed + upper_remaining(i, occupied) < state['M']:
            return

        cand = candidates[i]
        for slot in cand['eligible']:
            if slot in occupied:
                continue
            consumed = [slot]
            if cand['is_double']:
                blocks = (base_slots.get(slot) or {}).get('double_blocks')
                if blocks:
                    if blocks in occupied:
                        continue
                    consumed.append(blocks)
            assign[slot] = i
            for s in consumed:
                occupied.add(s)
            recurse(i + 1, placed + 1, assign, occupied)
            for s in consumed:
                occupied.discard(s)
            del assign[slot]
            if truncated[0]:
                return
        # Leave candidate i unplaced.
        recurse(i + 1, placed, assign, occupied)

    recurse(0, 0, {}, set())
    return state['assigns'], truncated[0]


def solve_v1(definitions, config, rules, compat_idx, request_body):
    """Solve module->slot placement for a `{core, base, modules, ...}` request.

    Returns (response, err, status). The response carries up to `max_solutions`
    ranked placements (default 3, clamped to [1, 5]) — placements + scores only,
    NO `resolved` pin block. The client re-fetches pins from /validate on the
    layout it picks (spec 010). Conflict/warning counts come from reusing
    `resolve()` internally; no conflict logic is duplicated here.
    """
    if not isinstance(request_body, dict):
        return None, ('invalid_request', "Request body must be a JSON object."), 400

    core = request_body.get('core')
    base = request_body.get('base')
    modules = request_body.get('modules')
    options = request_body.get('options') or {}

    if not isinstance(base, str) or not base:
        return None, ('invalid_request', "Field `base` is required."), 400
    if not isinstance(modules, list):
        return None, ('invalid_request', "Field `modules` must be an array."), 400
    if len(modules) > MAX_MODULES:
        return None, ('invalid_request',
                      f"`modules` exceeds the maximum of {MAX_MODULES} entries."), 400

    # max_solutions: default 3, clamp to [1, 5] (out-of-range clamped, not rejected).
    try:
        max_solutions = int(request_body.get('max_solutions', 3))
    except (TypeError, ValueError):
        max_solutions = 3
    max_solutions = max(1, min(5, max_solutions))

    base_canon, core_canon, _base_has_core, err = _resolve_core_base(
        definitions, core, base)
    if err is not None:
        code, message, status = err
        return None, (code, message), status

    base_def = definitions[base_canon]
    base_display = _to_display_id(base_canon)
    core_for_resolve = _to_display_id(core_canon) if core_canon else None
    i2c_overrides, ov_err = _extract_i2c_overrides(options)
    if ov_err is not None:
        return None, ov_err, 400

    # Partition requested modules into placeable candidates vs always-unplaced.
    candidates = []
    always_unplaced = []
    for m in modules:
        if not isinstance(m, str) or not m:
            return None, ('invalid_request',
                          "Each entry in `modules` must be a non-empty string."), 400
        canon = _to_canonical_id(m)
        mdef = definitions.get(canon)
        if mdef is None:
            always_unplaced.append({
                'module': m,
                'reason': 'unknown_module',
                'detail': f"Module '{m}' is not known to WisMAP.",
            })
            continue
        # CORE placement is owned by the top-level `core` field, never the solver.
        eligible = [s for s in compat_idx.get(canon, {}).get(base_display, [])
                    if s != 'CORE']
        if not eligible:
            always_unplaced.append({
                'module': _to_display_id(canon),
                'reason': 'incompatible_with_base',
                'detail': f"{_to_display_id(canon)} has no compatible slot on {base_display}.",
            })
            continue
        candidates.append({
            'display': _to_display_id(canon),
            'canon': canon,
            'is_sensor': mdef.get('type') == 'WisSensor',
            'is_double': bool(mdef.get('double')) and mdef.get('type') == 'WisSensor',
            'eligible': eligible,
        })

    assignments, truncated = _enumerate_assignments(candidates, base_def)
    if not assignments:
        assignments = [{}]  # nothing placeable → a single empty layout

    # Dedupe by slot->module map, score each via resolve(), then rank.
    seen = set()
    scored = []
    for assign in assignments:
        slot_map = {slot: candidates[idx]['display'] for slot, idx in assign.items()}
        key = tuple(sorted(slot_map.items()))
        if key in seen:
            continue
        seen.add(key)

        resp, resolve_err, _ = resolve(
            definitions, config, rules,
            core_for_resolve, base_display, slot_map, i2c_overrides)
        if resolve_err is not None:
            continue  # defensive: validated, compatible input shouldn't hard-error

        error_count = len(resp['conflicts'])
        warning_count = len(resp['warnings'])
        placed_idx = set(assign.values())
        sensors_on_top = sum(
            1 for slot, idx in assign.items()
            if candidates[idx]['is_sensor'] and _slot_layer(base_def, slot) == 'top'
        )
        unplaced = list(always_unplaced)
        for j, cand in enumerate(candidates):
            if j not in placed_idx:
                unplaced.append({
                    'module': cand['display'],
                    'reason': 'no_free_slot',
                    'detail': f"No free compatible slot for {cand['display']} on {base_display}.",
                })

        ordered_slots = sorted(slot_map, key=_slot_sort_index)
        slot_order_repr = tuple((_slot_sort_index(s), slot_map[s]) for s in ordered_slots)
        scored.append({
            'sort_key': (-len(slot_map), error_count, warning_count,
                         -sensors_on_top, slot_order_repr),
            'solution': {
                'valid': error_count == 0 and not unplaced,
                'error_count': error_count,
                'warning_count': warning_count,
                'conflicts': resp['conflicts'],
                'warnings': resp['warnings'],
                'sensors_on_top': sensors_on_top,
                'slots': [{'slot': s, 'module': slot_map[s]} for s in ordered_slots],
                'unplaced': unplaced,
            },
        })

    scored.sort(key=lambda x: x['sort_key'])
    solutions = []
    for rank, item in enumerate(scored[:max_solutions], start=1):
        sol = item['solution']
        solutions.append({
            'rank': rank,
            'valid': sol['valid'],
            'error_count': sol['error_count'],
            'warning_count': sol['warning_count'],
            'conflicts': sol['conflicts'],
            'warnings': sol['warnings'],
            'sensors_on_top': sol['sensors_on_top'],
            'slots': sol['slots'],
            'unplaced': sol['unplaced'],
        })

    warnings = []
    if truncated:
        warnings.append({
            'code': 'enumeration_capped',
            'severity': 'warning',
            'message': (f"Search exceeded {_SOLVE_NODE_CAP} nodes; results are "
                        f"best-effort and may not be maximum-placement."),
        })

    response = {
        'core': core_for_resolve,
        'base': base_display,
        'requested_modules': list(modules),
        'solution_count': len(solutions),
        'truncated': truncated,
        'solutions': solutions,
        'warnings': warnings,
    }
    return response, None, 200
