#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Integration tester charm for Loki Operator."""

import logging

import logging_loki  # type: ignore
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer, ProviderTopology
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus


class LokiTesterCharm(CharmBase):
    """A Loki Operator Client Charm."""

    def __init__(self, *args):
        super().__init__(*args)

        self._loki_consumer = LokiPushApiConsumer(self)

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.loki_tester_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.log_error_action, self._on_log_error_action)
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_joined,
            self._on_loki_push_api_endpoint_joined,
        )
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_departed,
            self._on_loki_push_api_endpoint_departed,
        )

        self.topology = ProviderTopology.from_charm(self)

    def _setup_logging(self, handler: dict = None) -> None:
        """Ensure logging is configured correctly."""
        handler = handler or {}
        logger = logging.getLogger("Loki-Tester")
        logger.setLevel(logging.INFO)

        handlers = {"console": logging.StreamHandler()}
        handlers.update(handler)

        for k, v in handlers.items():
            # Give each handler a "name" property which matches so we can find it
            v.name = k

        existing_handlers: dict[str, logging.Handler] = {v.name: v for v in logger.manager.loggerDict.values() if type(v) == logging.Handler}  # type: ignore

        if set(handlers.keys()) == set(existing_handlers.keys()):
            # Nothing to do
            return

        to_remove = [v for k, v in existing_handlers.items() if k not in handlers]
        to_add = [v for k, v in handlers.items() if k not in existing_handlers]

        # Remove loggers we don't want anymore
        for h in to_remove:
            logger.removeHandler(h)

        # Add any missing loggers whichshould be there
        for h in to_add:
            logger.addHandler(h)

        self.logger = logger
        logger.debug(
            "Configured logging with {} handlers: {}".format(
                len(handlers.keys()), ", ".join(handlers.keys())
            )
        )

    def _on_pebble_ready(self, _) -> None:
        """Set the unit to ready when Pebble is ready."""
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, _):
        """Handle changed configuration."""
        self.set_logger()
        self.log("debug", "Handling configuration change")

    def _on_update_status(self, _):
        self.set_logger()
        self.log("debug", "Updating status")

    def _on_loki_push_api_endpoint_joined(self, _):
        self.set_logger()
        self.log("debug", "Loki push API endpoint joined")

    def _on_loki_push_api_endpoint_departed(self, _):
        # TODO (multi-logger): remove only the logger whose endpoint departed
        self.set_logger(local_only=True)
        self.log("debug", "Loki push API endpoint departed")

    def _on_log_error_action(self, event):
        self.set_logger()
        message = event.params["message"]
        logged = self.log("error", message)
        if logged:
            event.set_results({"message": "Error message successfully logged"})
        else:
            event.fail("Failed to log error message")

    def set_logger(self, local_only=False):
        if local_only:
            self._setup_logging({})
            return

        tags = self.topology.as_promql_label_dict()
        log_endpoints = self._loki_consumer.loki_endpoints

        loki_handlers = {}
        if log_endpoints:
            logging_loki.emitter.LokiEmitter.level_tag = "level"
            # TODO (multi-logger): create loggers for each endpoint

            loki_handlers.update(
                {
                    "loki": logging_loki.LokiHandler(
                        url=log_endpoints[0]["url"], version="1", tags=dict(tags)
                    )
                }
            )
            # TODO (multi-logger): each logger will need a different name

        self._setup_logging(loki_handlers)

        if loki_handlers:
            self.log("debug", "Successfully set Loki Logger")

    def log(self, level, msg):
        try:
            getattr(self.logger, level)(msg)
            return True
        except AttributeError:
            return False


if __name__ == "__main__":
    main(LokiTesterCharm)
