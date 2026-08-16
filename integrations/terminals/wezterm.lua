-- coffee-paladin in the WezTerm status bar.
--
-- Drop into ~/.config/wezterm/ and `require` it from wezterm.lua, or paste
-- the handler into an existing config. The `update-status` event fires every
-- status_update_interval milliseconds; the paladin snapshot itself refreshes
-- every 15 s, so polling faster only reheats the same file.
--
-- The script's ANSI colors are stripped here rather than interpreted:
-- set_right_status accepts wezterm.format elements, not raw escapes, and a
-- truthful monochrome line beats a garbled colored one.

local wezterm = require 'wezterm'

wezterm.on('update-status', function(window, pane)
  local ok, stdout = wezterm.run_child_process {
    '/bin/bash', '-c',
    'NO_COLOR=1 ~/.coffee-paladin/statusline.sh </dev/null | head -1',
  }
  if ok and stdout and #stdout > 0 then
    window:set_right_status(wezterm.format {
      { Text = ' ' .. stdout:gsub('\n', '') .. ' ' },
    })
  else
    window:set_right_status('')
  end
end)

return { status_update_interval = 15000 }
