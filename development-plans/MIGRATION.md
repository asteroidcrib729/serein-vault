# Upgrading existing data

The current Serein Vault 1.2.0 is academically validated for local study/demo use. Migration remains explicit, source-preserving, and backup-first. Current EXE/MSIX draft previews come from the new source, never the archived executable. See [academic readiness](ACADEMIC-READINESS.md).

## Password-only Serein Vault 1.0

Use **Upgrade an older password-only vault** on the account screen. Select the existing `.svdb` file, choose a username, and enter the original password. The app saves an encrypted `.before-account-<id>.svdb` backup beside the original, then atomically upgrades the original file to the username/password/recovery-key format. Save the recovery key displayed after upgrading.

The RSA identity, item keys, history, and existing message/file formats remain compatible. If backup or persistence fails, the original is preserved. The old password-only format has no recovery-key reset mechanism; a forgotten original password cannot be bypassed by selecting a username. Old backup files stay password-only and need their own upgrade if restored.

## Original EncryptZone prototype

The current application never reads `Pass.txt`, `File_Keys.json`, or `Message_Keys.json` automatically. Create a new Serein Vault with a new password first. The old app's password was only a UI gate; its Fernet keys were not derived from that password.

1. Sign up and log in to a Serein account. Keep a separate backup of all old encrypted files and surviving key JSON files. Do not run the deprecated executable against them.
2. Open **Account & backups → File keys…** and select an old `File_Keys.json`. Pretty-printed JSON is supported. The entire import validates before a single encrypted database transaction saves the records.
3. Select the imported key in **History & recovery**, choose **Recover legacy file…**, and select the matching encrypted file and a separate output. The file can have moved since encryption; its old path is only a label.
4. Use **Message keys…** to import `Message_Keys.json`. Select an imported message and use **Recover message**. Legacy messages come from their archived JSON ciphertext, whereas new-message decryption reads the actual token entered in Messages.
5. Optionally use **Password hash…** to archive an old `Pass.txt` hash inside the encrypted database. It does not authenticate the new vault or change its password.
6. Verify recovered contents, save an encrypted vault backup, and test that it opens before deciding what to do with old plaintext key files. Imports preserve their sources; removing them requires your separate action.

The sample tracked `Pass.txt` has been removed from the current source tree. Prior Git commits still contain it and the old source. No production keys were found in the initial repository; there were no `File_Keys.json` or `Message_Keys.json` files to migrate automatically.

Legacy Fernet file recovery is limited to 64 MiB of encrypted input because the old format requires whole-message authentication. New file encryption streams and does not have that legacy size restriction. Legacy key JSON imports are limited to 10 MiB and 10,000 records.

Keys deleted by previous message encryption or overwritten by repeated file encryption cannot be reconstructed from a password hash. Find a surviving key-file backup if one exists. Never overwrite the only copy while attempting recovery.
