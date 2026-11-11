# RELEASE-006 · Permanent horse identity

`selection_id` remains the race-local runner key. A research signal may now carry a separate `horse_id`, `horse_id_source`, `horse_id_source_version`, `horse_identity_status` and `horse_identity_reason`. Existing rows retain their candidate payload and default to UNATTESTED with a null permanent ID.

The recording API accepts an `AttestedHorseIdentity` from a trusted verifier. It checks the race and selection binding, source and version, and rejects disagreements about the permanent ID. The watcher supplies no attestation today. Raw start numbers, names and provisional DNT/UELN matches do not enter this contract. No historical identity was backfilled.

The current watcher can still save the complete candidate as research evidence. Primary qualification remains blocked until a trusted adapter verifies the entire field and authentic original WIN evidence. The tests exercise storage and rejection of mismatched attestations with controlled inputs. No live provider identity has been accepted.
