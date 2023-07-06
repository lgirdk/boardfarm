# Architecture

Boardfarm follows plugin architecture pattern. Thus, It is easier to extend the framework and customize.
The framework is structured in the way where core components and plugins are separately placed.

The plugins can perform the actions supported by the core.
Plugins register themselves with the application. A plugin can be unregistered and a different plugin could be registered for different scenarios.

## Guildelines to develop a plugin

TODO:

## Plugins available in Boardfarm

These available plugins demonstrate how the architecture works and it serve as a reference for users. These examples can showcase different types of functionality that can be added or modified through plugins.

## Core plugins

Core plugins deal with the following

- commandline support
- deployment of device
- device reservation
- post device deployment configuration
- device release

## Device plugins

Device plugins works with different kinds of devices and servers.

### Server specific

- server boot
- server configure

### Device Specific

- register device
- device boot
- attached devices boot & configuration
- shutdown device
