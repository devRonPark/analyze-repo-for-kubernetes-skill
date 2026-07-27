/*!
 * express
 * Copyright(c) 2009-2013 TJ Holowaychuk
 * Copyright(c) 2013 Roman Shtylman
 * Copyright(c) 2014-2015 Douglas Christopher Wilson
 * MIT Licensed
 */

'use strict';

/**
 * Module dependencies.
 * @private
 */

var finalhandler = require('finalhandler');
var debug = require('debug')('express:application');
var View = require('./view');
var http = require('node:http');
var methods = require('./utils').methods;
var compileETag = require('./utils').compileETag;
var compileQueryParser = require('./utils').compileQueryParser;
var compileTrust = require('./utils').compileTrust;
var resolve = require('node:path').resolve;
var once = require('once')
var Router = require('router');

/**
