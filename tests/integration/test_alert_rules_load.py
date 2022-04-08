#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import IPAddressWorkaround, is_loki_up, loki_rules

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}
rules_app = "loki-tester"
rules_app2 = "loki-tester2"
rules_app3 = "cos-config"


@pytest.mark.abort_on_fail
async def test_deploy(ops_test, loki_charm):
    """Deploy Loki and make sure it's up with no rules files.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(loki_charm, resources=resources, application_name=app_name)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
        assert ops_test.model.applications[app_name].units[0].workload_status == "active"

    assert await is_loki_up(ops_test, app_name)

    rules_before_relation = await loki_rules(ops_test, app_name)
    assert len(rules_before_relation) == 0


@pytest.mark.abort_on_fail
async def test_first_relation_one_alert_rule(ops_test, loki_tester_charm):
    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=rules_app,
        ),
    )

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(
            apps=[app_name, rules_app], status="active", timeout=1000
        )

    rules_after_relation = await loki_rules(ops_test, app_name)
    assert len(rules_after_relation) == 1


@pytest.mark.abort_on_fail
async def test_second_relation_second_alert_rule(ops_test, loki_tester_charm):
    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=rules_app2,
        ),
    )

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app2)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(
            apps=[app_name, rules_app2], status="active", timeout=1000
        )

    rules_after_relation = await loki_rules(ops_test, app_name)
    assert len(rules_after_relation) == 2


@pytest.mark.abort_on_fail
async def test_remove_app_one_alert_rules_is_retained(ops_test):
    await ops_test.model.applications[rules_app].remove()
    await ops_test.model.block_until(lambda: rules_app not in ops_test.model.applications)

    rules_after_delete_relation = await loki_rules(ops_test, app_name)
    assert len(rules_after_delete_relation) == 1


@pytest.mark.abort_on_fail
async def test_wrong_alert_rule(ops_test):
    await ops_test.model.deploy(
        "ch:cos-configuration-k8s",
        application_name=rules_app3,
        channel="edge",
        config={
            "git_repo": "https://github.com/canonical/loki-k8s-operator",
            "git_branch": "itest-refactor",
            "loki_alert_rules_path": "tests/sample_rule_files/error",
        },
    )

    # force an update, just in case the files showed up on disk after the last hook fired
    action = await ops_test.model.applications[rules_app3].units[0].run_action("sync-now")
    await action.wait()

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app3)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(apps=[app_name], status="blocked", timeout=1000)
