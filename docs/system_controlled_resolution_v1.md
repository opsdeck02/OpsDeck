# System Controlled Resolution V1

System-generated exceptions stay open until fresh data recomputation confirms the underlying issue is gone.

## Why manual resolution is blocked

- Completing an action means the team acted.
- It does not prove the risk or movement problem is actually cleared.
- Fresh stock, shipment, port, or inland data must confirm the condition no longer exists.

## Allowed user actions

- assign or change owner
- add comments
- move status between `open` and `in_progress`
- start or complete the linked action

## Auto-resolution behavior

- engine-generated exceptions cannot be manually set to `resolved` or `closed`
- recomputation marks them `resolved` when the matching condition disappears
- open counts only change after recomputation resolves the case

## Limitations

- this version assumes trigger-source-based exceptions are system-generated
- manual closure is not exposed for those cases
- action completion and exception resolution are intentionally separate states

## Future ideas

- separate lifecycle for manually created exceptions if introduced later
- clearer UI labels for acted vs verified-cleared
- audit view showing the recomputation event that resolved an exception
