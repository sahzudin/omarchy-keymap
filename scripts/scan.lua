-- Evaluate Omarchy's Lua configuration against a recording Hyprland shim.
-- This produces the effective source-defined bindings without requiring the
-- compositor or trying to parse arbitrary Lua as text.

local config = arg[1] or ((os.getenv("HOME") or "") .. "/.config/hypr/hyprland.lua")
local records = {}

local function trim(value)
  return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local modifier_order = { SUPER = 1, SHIFT = 2, CTRL = 3, CONTROL = 3, ALT = 4 }

local function normalize_shortcut(value)
  local modifiers = {}
  local key = ""
  for part in tostring(value or ""):gmatch("[^+]+") do
    local token = trim(part)
    local upper = token:upper()
    if modifier_order[upper] then
      if upper == "CONTROL" then upper = "CTRL" end
      modifiers[upper] = true
    else
      key = token
    end
  end

  local ordered = {}
  for _, name in ipairs({ "SUPER", "SHIFT", "CTRL", "ALT" }) do
    if modifiers[name] then table.insert(ordered, name) end
  end
  if key ~= "" then table.insert(ordered, key) end
  return table.concat(ordered, " + ")
end

local function lua_literal(value)
  local value_type = type(value)
  if value_type == "string" then
    return string.format("%q", value)
  elseif value_type == "number" or value_type == "boolean" then
    return tostring(value)
  elseif value_type == "nil" then
    return "nil"
  elseif value_type == "table" then
    local parts = {}
    local keys = {}
    local length = #value
    for index = 1, length do
      table.insert(parts, lua_literal(value[index]))
    end
    for key in pairs(value) do
      if not (type(key) == "number" and key >= 1 and key <= length and math.floor(key) == key) then
        table.insert(keys, key)
      end
    end
    table.sort(keys, function(left, right) return tostring(left) < tostring(right) end)
    for _, key in ipairs(keys) do
      local prefix
      if type(key) == "string" and key:match("^[%a_][%w_]*$") then
        prefix = key .. " = "
      else
        prefix = "[" .. lua_literal(key) .. "] = "
      end
      table.insert(parts, prefix .. lua_literal(value[key]))
    end
    return "{ " .. table.concat(parts, ", ") .. " }"
  end
  return "nil"
end

local function call_expression(path, ...)
  local values = {}
  for index = 1, select("#", ...) do
    values[index] = lua_literal(select(index, ...))
  end
  return path .. "(" .. table.concat(values, ", ") .. ")"
end

local function dispatcher_proxy(path)
  return setmetatable({ __keymap_dispatcher = true, path = path }, {
    __index = function(self, key)
      return dispatcher_proxy(self.path .. "." .. tostring(key))
    end,
    __call = function(self, ...)
      local expression = call_expression(self.path, ...)
      local first = select(1, ...)
      return {
        __keymap_dispatcher = true,
        expression = expression,
        kind = self.path == "hl.dsp.exec_cmd" and "exec" or "lua",
        argument = self.path == "hl.dsp.exec_cmd" and tostring(first or "") or "",
      }
    end,
  })
end

local noop
noop = setmetatable({}, {
  __index = function() return noop end,
  __call = function() return noop end,
})

local function copy_options(options)
  local out = {}
  if type(options) ~= "table" then return out end
  for key, value in pairs(options) do
    if key ~= "description" then
      local kind = type(value)
      if kind == "string" or kind == "number" or kind == "boolean" then
        out[key] = value
      end
    end
  end
  return out
end

local function record_bind(keys, dispatcher, options)
  options = options or {}
  local supported = type(dispatcher) == "table" and dispatcher.__keymap_dispatcher == true
  table.insert(records, {
    shortcut = normalize_shortcut(keys),
    description = options.description,
    dispatcher = supported and dispatcher.expression or "",
    kind = supported and dispatcher.kind or "unsupported",
    argument = supported and dispatcher.argument or "",
    options = copy_options(options),
    supported = supported,
  })
  return noop
end

local function unbind(keys)
  local wanted = normalize_shortcut(keys)
  local kept = {}
  for _, record in ipairs(records) do
    if record.shortcut ~= wanted then table.insert(kept, record) end
  end
  records = kept
end

hl = setmetatable({
  dsp = dispatcher_proxy("hl.dsp"),
  bind = record_bind,
  unbind = unbind,
  get_config = function() return nil end,
  get_active_window = function() return nil end,
  on = function() return noop end,
  timer = function() return noop end,
  config = function() return noop end,
  exec_cmd = function() return noop end,
  dispatch = function() return noop end,
}, {
  __index = function() return noop end,
})

local function json_quote(value)
  return '"' .. tostring(value):gsub('[%z\1-\31\\"]', function(character)
    local replacements = {
      ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
      ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t',
    }
    return replacements[character] or string.format("\\u%04x", character:byte())
  end) .. '"'
end

local function is_array(value)
  local length = #value
  for key in pairs(value) do
    if type(key) ~= "number" or key < 1 or key > length or math.floor(key) ~= key then
      return false
    end
  end
  return true
end

local function json_encode(value)
  local kind = type(value)
  if kind == "nil" then return "null" end
  if kind == "boolean" or kind == "number" then return tostring(value) end
  if kind == "string" then return json_quote(value) end
  if kind ~= "table" then return "null" end

  local parts = {}
  if is_array(value) then
    for index = 1, #value do table.insert(parts, json_encode(value[index])) end
    return "[" .. table.concat(parts, ",") .. "]"
  end

  local keys = {}
  for key in pairs(value) do table.insert(keys, tostring(key)) end
  table.sort(keys)
  for _, key in ipairs(keys) do
    table.insert(parts, json_quote(key) .. ":" .. json_encode(value[key]))
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

local file = io.open(config, "r")
if not file then
  io.stderr:write("Could not read " .. config .. "\n")
  os.exit(1)
end
file:close()

local ok, failure = pcall(dofile, config)
if not ok then
  io.stderr:write("Could not evaluate " .. config .. ": " .. tostring(failure) .. "\n")
  os.exit(1)
end

print(json_encode(records))
