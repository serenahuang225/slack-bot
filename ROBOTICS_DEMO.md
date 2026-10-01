# Atlas robotics demo: three accounts

All messages below are fictional. Atlas is a small wheeled robot. Its motor controller is the circuit board that drives its motors; its encoder is a sensor that measures motion. The enclosure is the housing around the electronics. A lead time is how long a supplier takes to deliver a part.

## 1. Prepare the channel and bot

Create a public test channel `#atlas-team`. Join with all three accounts and invite EverCurrent Digest. Put the channel's actual Slack ID in `.env`:

```dotenv
CHANNEL_PROJECTS={"C_REPLACE_WITH_CHANNEL_ID":"atlas"}
PROJECT_ADMIN_IDS=U_REPLACE_WITH_SERENA_MIT_MEMBER_ID
```

Keep your existing Slack tokens. Do not replace them with placeholders. The admin setting takes a Slack member ID, not the display name `serena mit`.

Run `source .venv/bin/activate` and then `digest slack` for live messages. If you already posted the demo, run `digest backfill` in a second terminal with the environment activated to import the earlier messages.

Each account opens its own DM with the bot and sends:

- **serena mit — mechanical engineer:** `setup mechanical atlas`
- **serena — electrical engineer:** `setup electrical atlas`
- **serenahuang225 — supply-chain lead:** `setup supply atlas`

From serena mit's bot DM, send `phase atlas prototype`.

The accounts talk to one another in #atlas-team. Their private DMs with the bot are for setup, questions and digests. The bot cannot read human-to-human DMs.

## 2. Round one: prototype design

Post each numbered message as a NEW channel message under the specified account. Paste only the quoted content. Names written inside messages are plain text; you can select real Slack @mentions when desired.

**1 — serena mit**
> Atlas enclosure design decision: use an aluminum housing for the motor controller. I own the mechanical CAD and mounting-hole tolerance review. I will share the updated design tomorrow.

**2 — serena**
> PCB electrical update: the motor controller power and voltage tests passed at 12V. I own the controller wiring check before robot integration.

**3 — serenahuang225**
> Supplier update: the motor controller shipment is confirmed for Thursday. The order contains three boards for prototype assembly. I own delivery tracking.

**4 — serena mit**
> Mechanical assembly is blocked: the controller mounting holes do not match the enclosure CAD. serena, please confirm the board dimensions before I revise the housing.

**5 — serena, REPLY IN THE THREAD of message 4**
> Confirmed: the controller board is 80 by 60 mm, and the mounting-hole spacing is 70 by 50 mm. Please use these dimensions for the enclosure revision.

**6 — serenahuang225**
> Supplier risk: the encoder vendor increased lead time from one week to four weeks. The robot integration milestone may be delayed. I am requesting quotes from alternate suppliers.

**7 — serena**
> Encoder electrical requirement: any replacement sensor must work with the 5V power supply and the existing connector. Do not place a replacement order until I confirm compatibility.

**8 — serena mit**
> Mechanical decision: reserve 10 mm of clearance above the controller for a heat sink. This changes the enclosure height but not the external mounting points.

Now send `digest` separately from each account's DM with the bot. Everyone sees the same underlying channel but a different ranking. Mechanical should emphasize housing/assembly, electrical should emphasize controller/sensor compatibility, and supply should emphasize vendor/shipment risk. It returns up to five items, so some overlap is expected.

## 3. Round two: validation and a cross-team blocker

From serena mit's bot DM: `phase atlas validation`.

**9 — serena**
> Validation blocker: the motor controller failed the thermal test after 20 minutes. It reached 92 degrees Celsius, above our demo project's 80-degree limit. Further robot testing is blocked until we improve cooling. I own the electrical retest.

**10 — serena mit, REPLY IN THE THREAD of message 9**
> I will revise the enclosure ventilation and add a heat sink. serena, please send the temperature measurements. I own the mechanical cooling design and can finish it by tomorrow afternoon.

**11 — serenahuang225, REPLY IN THE THREAD of message 9**
> Heat-sink procurement risk: our usual supplier cannot deliver until next week. I found a local vendor with stock, but need serena mit to approve its dimensions before placing the order.

**12 — serenahuang225**
> Alternate encoder supplier found: delivery is two days and the price is $18 instead of $12. Order is waiting for serena's electrical compatibility approval.

Ask these questions in the corresponding bot DMs:

- serena mit: `Why is robot testing blocked?`
- serena: `What electrical requirements does the replacement encoder need to meet?`
- serenahuang225: `Whose approval do I need before ordering the heat sink?`

These questions exercise retrieval of earlier thread context. With Gemini enabled the bot generates answers with source references. Offline mode displays matching excerpts instead.

From serenahuang225's bot DM: `focus heat sink supplier delivery`. This preference persists until changed or cleared with `focus clear`. Request `digest` again to see the changed priorities. A role or phase change changes ranking; it does not rewrite the source facts.

## 4. Round three: resolve a blocker

**13 — serena mit, REPLY IN THE THREAD of message 4**
> Resolved: the enclosure CAD now matches the controller mounting holes. Mechanical fit-check passed, and assembly can proceed.

**14 — serena, REPLY IN THE THREAD of message 9**
> Resolved: the revised enclosure and new heat sink passed the 20-minute thermal retest at 72 degrees Celsius. The cooling blocker is closed and robot testing can resume.

Request new digests. These two resolved threads should drop out. Keep resolutions in their original threads so the app can connect them to the earlier blockers.

## 5. Round four: production priorities

From serena mit's bot DM: `phase atlas production`.

**15 — serenahuang225**
> Production supplier risk: the vendor requires a minimum order of 100 encoders, but our pilot manufacturing run needs only 20. I need a purchase decision before Friday to avoid a shipment delay.

**16 — serena mit**
> Manufacturing update: the enclosure assembly instructions and tolerance drawings are ready for the 20-robot pilot build. I still need the final material specification from our supplier.

**17 — serena**
> Production electrical update: the PCB power-test procedure is ready. Each controller must pass the voltage and sensor checks before installation in a robot.

Request digests and compare the new manufacturing and supplier priorities. Click Less relevant on an item and request another digest: that specific issue receives a lower score, but may still appear if there are few candidates.

## Optional: show the other two brief roles

Temporarily send `setup manager atlas` or `setup product atlas` from one account, then request `digest`. Setup changes that account's role and preserves its existing focus. Restore it afterward using the original setup command. With only three accounts, all five roles do not need to be active simultaneously.

## Demonstrate documentation and changes

Send `docs atlas` to browse the automatically collected thread and file knowledge. Upload `fixtures/atlas-spec.md` to the configured channel while the bot runs, then request `docs atlas` again to see the reference document.

Send `digest` once to establish a checkpoint. Post a new update or reply with a resolution in an existing thread, then send `changes` before requesting the next digest. New and resolved sources appear in the change report. Send `status atlas` to see current blockers, risks and decisions, including older open issues. Send `help` for all commands or `settings` to open the role/projects/responsibilities form.

No messages in this document have been posted automatically.
