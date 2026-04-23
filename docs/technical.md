# Crimson Desert 1.04 patch — save-migration field-dropout bug

**Reporter:** Luca (player, Steam)
**Date of observation:** April 23, 2026
**Build:** Patch 1.04 (released same day)
**Severity:** Data loss affecting multiple save-game subsystems; one class of loss is user-visible (mounts missing from summon menu), others are silent but substantial.
**Method:** Offline binary diff of pre-patch `save.save` vs post-patch `save.save` vs pre-patch-client re-saved `save.save`, parsed through the published PARC / reflection container format used by the game's save loader.

---

## Summary

The 1.04 save-loader migration path silently drops fields from serialized objects in multiple save subsystems during first load of a pre-1.04 save. The affected records are preserved in the save file but are now incomplete relative to the 1.04 schema. In at least one subsystem (`MercenaryClanSaveData`) the dropped fields produce visible gameplay loss: summonable mounts that the player unlocked through normal in-game progression no longer appear in the mount menu and cannot be summoned.

This is not an editor-caused issue. The affected save was never modified by a third-party tool. The affected mounts were unlocked through normal mission and objective completion.

## Observed size deltas across SaveData blocks

Comparing the same player save file across three states:

- **before**: pre-1.04 save, last written by the 1.03-or-earlier client
- **after**: the same save after being loaded and written by the 1.04 client
- **reloaded**: the same save after being re-opened in the prior client build (rollback) and re-saved

| SaveData block                         | before → after delta |
|----------------------------------------|----------------------|
| `StoreSaveData`                        | **−170,165 bytes** (≈28% of block mass lost) |
| `FactionSpawnStageManagerSaveData`     | **−10,912 bytes** |
| `QuestSaveData`                        | +5,179 bytes (normal growth) |
| `InventorySaveData`                    | −2,140 bytes |
| `FriendlySaveData`                     | +1,594 bytes |
| `FieldNPCSaveData` (×447 entries)      | +894 bytes |
| `MercenaryClanSaveData`                | +625 bytes (net; see below) |

The `StoreSaveData` loss in particular is large enough that I expect other players have noticed vendor stock/price state resetting after the patch, even if they cannot articulate the cause. `FactionSpawnStageManagerSaveData` and `FieldNPCSaveData` deltas suggest world-state drift as well.

Rolling the client back and re-saving restores the pre-1.04 schema layout for these blocks (the "reloaded" save I kept shows `StoreSaveData` back up to 612,608 bytes versus the post-patch 442,443). That tells me the data that the 1.04 loader drops is *recoverable from the old save file*, i.e. the loader is parsing it incorrectly, not losing it on disk.

## The mount sub-symptom: concrete evidence

Within `MercenaryClanSaveData._mercenaryDataList`, the 1.04 schema appears to introduce:

- `_ownedCharacterKey` (u32, 4B) — present on the new Cloud Cruiser (`characterKey=1002042`) that I unlocked post-patch
- `_isMainMercenary` (u8, 1B) — present on Cloud Cruiser; present on most migrated records

And legacy field `_lastSummoned` (u8, 1B) is being retained on some records and absent on others with no discernible pattern.

Of 95 merc records in my pre-patch save, the 1.04 first-load correctly migrated 91 (most grew by +1 to +9 bytes, consistent with the schema additions). **Four records exhibit a "field dropout" signature where pre-existing fields were cleared rather than preserved through the migration**:

| charKey | mercNo | label               | before fields   | after fields     | delta |
|---------|--------|---------------------|-----------------|------------------|-------|
| 1003918 | 5573   | Silver Fang (wolf)  | owned=n mm=**Y** ls=Y | owned=n mm=**n** ls=Y | mm lost |
| 1003919 | 5629   | Snow White Deer     | owned=n mm=**Y** ls=Y | owned=n mm=**n** ls=Y | mm lost |
| 1002043 | 3663   | Balloon Summoner 3  | owned=n mm=**Y** ls=n | owned=n mm=**n** ls=n | mm lost |
| 31377   | 3859   | *(unknown NPC/mount)* | owned=**Y** mm=**Y** ls=**Y** | owned=**n** mm=**n** ls=**n** | **all three lost** |

(`mm` = `_isMainMercenary`, `ls` = `_lastSummoned`)

A fifth record has a different failure mode:

| charKey | mercNo | label            | before         | after          |
|---------|--------|------------------|----------------|----------------|
| 1003120 | 38     | Kliff's Tiuta   | owned=**Y** mm=n ls=Y | owned=**n** mm=n ls=Y |

— where `_ownedCharacterKey` was dropped but the record was otherwise migrated (size shrank by 3 bytes).

In every case, re-loading the save in the pre-1.04 client and re-saving restored the dropped fields. That byte-pattern evidence is hard to reconcile with anything but a migration bug in the 1.04 save loader.

## Player-visible effect

In the post-1.04 save, the following mounts that were previously summonable no longer appear in the mount menu:

- Silver Fang
- Snow White Deer
- Cloud Cart
- Sky Streaker

The Cloud Cruiser, a mount introduced in 1.04 that I unlocked after applying the patch, works correctly — because its record was written fresh with the new schema rather than migrated from old. Generic horses were also initially unsummonable after the patch but could be repaired via the in-game "mount heal" operation at a stable. The four mounts above cannot be repaired through that in-game path.

## Hypothesized root cause (speculative)

In the 1.04 save-loader, the migration step for certain reflection-serialized structs appears to enter a state where it clears bits in the member-present bitmap rather than translating them. The pattern of losses looks like the migration code is using the bit positions of pre-1.04 optional fields to *read* field presence, then re-writing the bitmap with 1.04 bit positions, and failing to translate the old bit positions to the new ones for a specific subset of types. Records that were simple enough not to hit the translation mis-map survived; records that carried certain flag combinations tripped it.

The `StoreSaveData` loss pattern suggests a similar kind of failure at higher volume — possibly the migration dropping entries from nested lists (store stock items, dropset entries, etc.) rather than just single bitmap fields.

## Workaround observed by affected players

1. Keep a backup of the pre-1.04 `save.save` file.
2. Re-install the pre-1.04 client build (or keep it available via Steam's rollback menu).
3. Open the pre-1.04 save in the old client. Move between zones, open your inventory, let the client re-touch and re-serialize state. Save.
4. Re-run the 1.04 client and load that save.
5. In-game, visit a stable and use the "mount heal" operation on any horses that are stuck.

This workaround restores `StoreSaveData`, `FactionSpawnStageManagerSaveData`, and generic-horse mount records, but does **not** restore the four quest-unlocked mounts listed above. Those remain inaccessible without further intervention.

## Recommendations

1. **Review the 1.04 `MercenarySaveData` migration path.** Look specifically at records where pre-1.04 had `_isMainMercenary` set. My data suggests the migration is clearing that bit for records that retain certain legacy flags (e.g. `_lastBreedingTime`, `_lastPaidTime`), possibly due to a bitmap-position collision between the removed `_lastSummoned` slot and the added `_isMainMercenary` / `_ownedCharacterKey` slots.

2. **Audit `StoreSaveData` migration.** The 170KB drop across the store save block is the largest observed anomaly and probably affects more players than the mount issue, even if those players haven't noticed yet. If store stock tables were silently halved, the economy is desynced with the design intent.

3. **Add a migration-integrity log.** On first 1.04 load of a pre-1.04 save, emit a log line per subsystem recording input byte count, output byte count, and number of records migrated vs. dropped. This would have caught the bug in internal QA if the delta was unexpected.

4. **Ship a repair pass in a subsequent patch** that detects "stuck" records in `MercenaryClanSaveData` — records whose `_characterKey` resolves to a mount definition that should be present in the mount menu but whose bitmap lacks fields the game now uses for menu filtering — and reinitializes them from the character-definition templates. A similar pass for `StoreSaveData` might need to pull stock defaults from the static game-content tables rather than the save.

5. **For affected players, document the rollback-save-reload workaround** in a support article. Without that documentation, players will assume their progression was lost rather than recoverable.

## Supporting artifacts available

I have offline byte-level diffs of the three save states and can make them available on request:

- `save_before.save` — pre-patch save, last written by the pre-1.04 client
- `save_after.save` — the same save after being opened once by the 1.04 client (the broken state)
- `save_reloaded.save` — the same save after being re-opened and saved by the pre-1.04 client (the partial-recovery state)
- PARC-level block-size delta report (reproducible from the above three files using the published `save_crypto` + `parc_serializer` modules from the NattKh community tool)
- Per-record field-presence transition table for all 95 entries in `MercenaryClanSaveData._mercenaryDataList`

The analysis methodology is non-privileged — everything was done by decrypting the save (ChaCha20 + HMAC-SHA256 + LZ4-HC using the documented `_SAVE_BASE_KEY`) and parsing the reflection container format. No game binary was decompiled. No game assets were extracted. Happy to share any of the above with a Pearl Abyss engineer who wants to reproduce the findings.
