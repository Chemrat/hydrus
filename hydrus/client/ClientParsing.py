import base64
import typing

import bs4
import collections
import html
import json
import re
import time
import urllib.parse
import warnings

from hydrus.core import HydrusConstants as HC
from hydrus.core import HydrusData
from hydrus.core import HydrusExceptions
from hydrus.core import HydrusNumbers
from hydrus.core import HydrusSerialisable
from hydrus.core import HydrusTags
from hydrus.core import HydrusText
from hydrus.core import HydrusTime

from hydrus.client import ClientGlobals as CG
from hydrus.client import ClientStrings
from hydrus.client.networking import ClientNetworkingFunctions
from hydrus.client.networking import ClientNetworkingJobs

try:
    
    import html5lib
    
    HTML5LIB_IS_OK = True
    
except ImportError:
    
    HTML5LIB_IS_OK = False
    

try:
    
    import lxml
    
    LXML_IS_OK = True
    
except ImportError:
    
    LXML_IS_OK = False
    

def ConvertParseResultToPrettyString( result ):
    
    ( ( name, content_type, additional_info ), parsed_text ) = result
    
    if content_type == HC.CONTENT_TYPE_URLS:
        
        ( url_type, priority ) = additional_info
        
        if url_type == HC.URL_TYPE_DESIRED:
            
            return 'downloadable/pursuable url (priority ' + str( priority ) + '): ' + parsed_text
            
        elif url_type == HC.URL_TYPE_SOURCE:
            
            return 'associable/source url (priority ' + str( priority ) + '): ' + parsed_text
            
        elif url_type == HC.URL_TYPE_NEXT:
            
            return 'next page url (priority ' + str( priority ) + '): ' + parsed_text
            
        elif url_type == HC.URL_TYPE_SUB_GALLERY:
            
            return 'sub-gallery url (priority ' + str( priority ) + '): ' + parsed_text
            
        
    elif content_type == HC.CONTENT_TYPE_MAPPINGS:
        
        try:
            
            if additional_info is None:
                
                combined_tag = parsed_text
                
            else:
                
                combined_tag = HydrusTags.CombineTag( additional_info, parsed_text )
                
            
            tag = HydrusTags.CleanTag( combined_tag )
            
        except:
            
            tag = 'unparsable tag, will likely be discarded'
            
        
        try:
            
            HydrusTags.CheckTagNotEmpty( tag )
            
        except HydrusExceptions.TagSizeException:
            
            tag = 'empty tag, will be discarded'
            
        
        return 'tag: ' + tag
        
    elif content_type == HC.CONTENT_TYPE_NOTES:
        
        note_name = additional_info
        
        return 'note "{}":\n{}'.format( note_name, parsed_text )
        
    elif content_type == HC.CONTENT_TYPE_HASH:
        
        ( hash_type, hash_encoding ) = additional_info
        
        try:
            
            hash = GetHashFromParsedText( hash_encoding, parsed_text )
            
            parsed_text = hash.hex()
            
        except Exception as e:
            
            parsed_text = 'Could not decode a hash from {}: {}'.format( parsed_text, repr( e ) )
            
        
        return '{} hash: {}'.format( hash_type, parsed_text )
        
    elif content_type == HC.CONTENT_TYPE_TIMESTAMP:
        
        timestamp_type = additional_info
        
        try:
            
            timestamp = int( parsed_text )
            
            timestamp_string = HydrusTime.TimestampToPrettyTime( timestamp )
            
        except:
            
            timestamp_string = 'could not convert to integer'
            
        
        if timestamp_type == HC.TIMESTAMP_TYPE_MODIFIED_DOMAIN:
            
            return 'source/post time: ' + timestamp_string
            
        
    elif content_type == HC.CONTENT_TYPE_TITLE:
        
        priority = additional_info
        
        return 'watcher page title (priority ' + str( priority ) + '): ' + parsed_text
        
    elif content_type == HC.CONTENT_TYPE_HTTP_HEADERS:
        
        header_name = additional_info
        
        return 'http header "{}": "{}"'.format( header_name, parsed_text )
        
    elif content_type == HC.CONTENT_TYPE_VETO:
        
        return 'veto: ' + name
        
    elif content_type == HC.CONTENT_TYPE_VARIABLE:
        
        temp_variable_name = additional_info
        
        return 'temp variable "' + temp_variable_name + '": ' + parsed_text
        
    
    raise NotImplementedError()
    

def ConvertParsableContentToPrettyString( parsable_content, include_veto = False ):
    
    try:
        
        pretty_strings = []
        
        content_type_to_additional_infos = HydrusData.BuildKeyToSetDict( ( ( ( content_type, name ), additional_infos ) for ( name, content_type, additional_infos ) in parsable_content ) )
        
        data = list( content_type_to_additional_infos.items() )
        
        for ( ( content_type, name ), additional_infos ) in data:
            
            if content_type == HC.CONTENT_TYPE_URLS:
                
                for ( url_type, priority ) in additional_infos:
                    
                    if url_type == HC.URL_TYPE_DESIRED:
                        
                        pretty_strings.append( 'downloadable/pursuable url' )
                        
                    elif url_type == HC.URL_TYPE_SOURCE:
                        
                        pretty_strings.append( 'associable/source url' )
                        
                    elif url_type == HC.URL_TYPE_NEXT:
                        
                        pretty_strings.append( 'gallery next page url' )
                        
                    elif url_type == HC.URL_TYPE_SUB_GALLERY:
                        
                        pretty_strings.append( 'sub-gallery url' )
                        
                    
                
            elif content_type == HC.CONTENT_TYPE_MAPPINGS:
                
                namespaces = [ namespace for namespace in additional_infos if namespace not in ( '', None ) ]
                
                if '' in additional_infos:
                    
                    namespaces.append( 'unnamespaced' )
                    
                
                if None in additional_infos:
                    
                    namespaces.append( 'any namespace' )
                    
                
                pretty_strings.append( 'tags: ' + ', '.join( namespaces ) )
                
            elif content_type == HC.CONTENT_TYPE_NOTES:
                
                note_names = sorted( additional_infos )
                
                s = 'notes:{}'.format( ', '.join( note_names ) )
                
                pretty_strings.append( s )
                
            elif content_type == HC.CONTENT_TYPE_HASH:
                
                s = 'hash: {}'.format( ', '.join( ( '{} in {}'.format( hash_type, hash_encoding ) for ( hash_type, hash_encoding ) in additional_infos ) ) )
                
                pretty_strings.append( s )
                
            elif content_type == HC.CONTENT_TYPE_TIMESTAMP:
                
                for timestamp_type in additional_infos:
                    
                    if timestamp_type == HC.TIMESTAMP_TYPE_MODIFIED_DOMAIN:
                        
                        pretty_strings.append( 'source/post time' )
                        
                    
                
            elif content_type == HC.CONTENT_TYPE_TITLE:
                
                pretty_strings.append( 'watcher page title' )
                
            elif content_type == HC.CONTENT_TYPE_HTTP_HEADERS:
                
                headers = sorted( [ header for header in additional_infos if header not in ( '', None ) ] )

                pretty_strings.append( 'http headers: ' + ', '.join( headers ) )
                
            elif content_type == HC.CONTENT_TYPE_VETO:
                
                if include_veto:
                    
                    pretty_strings.append( 'veto: ' + name )
                    
                
            elif content_type == HC.CONTENT_TYPE_VARIABLE:
                
                pretty_strings.append( 'temp variables: ' + ', '.join( additional_infos ) )
                
            
        
    except:
        
        return 'COULD NOT RENDER--probably a broken object!'
        
    
    pretty_strings = HydrusData.DedupeList( pretty_strings )
    
    pretty_strings.sort()
    
    if len( pretty_strings ) == 0:
        
        return 'nothing'
        
    else:
        
        return ', '.join( pretty_strings )
        
    

def GetChildrenContent( job_status, children, parsing_text, referral_url ):
    
    content = []
    
    for child in children:
        
        try:
            
            if isinstance( child, ParseNodeContentLink ):
                
                child_content = child.Parse( job_status, parsing_text, referral_url )
                
            elif isinstance( child, ContentParser ):
                
                child_content = child.Parse( {}, parsing_text )
                
            
        except HydrusExceptions.VetoException:
            
            return []
            
        
        content.extend( child_content )
        
    
    return content
    

def GetHashFromParsedText( hash_encoding, parsed_text ) -> bytes:
    
    encodings_to_attempt = []
    
    if hash_encoding == 'hex':
        
        encodings_to_attempt = [ 'hex', 'base64' ]
        
    elif hash_encoding == 'base64':
        
        encodings_to_attempt = [ 'base64' ]
        
    
    main_error_text = None
    
    for encoding_to_attempt in encodings_to_attempt:
        
        try:
            
            if encoding_to_attempt == 'hex':
                
                return bytes.fromhex( parsed_text )
                
            elif encoding_to_attempt == 'base64':
                
                return base64.b64decode( parsed_text )
                
            
        except Exception as e:
            
            if main_error_text is None:
                
                main_error_text = str( e )
                
            
            continue
            
        
    
    raise Exception( 'Could not decode hash: {}'.format( main_error_text ) )
    

def GetHashesFromParseResults( results ):
    
    hash_results = []
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_HASH:
            
            ( hash_type, hash_encoding ) = additional_info
            
            try:
                
                hash = GetHashFromParsedText( hash_encoding, parsed_text )
                
            except:
                
                continue
                
            
            hash_results.append( ( hash_type, hash ) )
            
        
    
    return hash_results
    

def GetHTMLTagString( tag: bs4.Tag ):
    
    # don't mess about with tag.string, tag.strings or tag.get_text
    # on a version update, these suddenly went semi bonkers and wouldn't pull text unless the types of the subtag were explicitly set
    # so we'll just do it ourselves
    
    all_strings = []
    
    try:
        
        for sub_tag in tag.descendants:
            
            if isinstance( sub_tag, bs4.Tag ) and sub_tag.name in ( 'br', 'p' ):
                
                all_strings.append( '\n' )
                
                continue
                
            
            if not isinstance( sub_tag, ( bs4.NavigableString, bs4.CData ) ):
                
                continue
                
            
            all_strings.append( str( sub_tag ) )
            
        
    except:
        
        all_strings = []
        
    
    return ''.join( all_strings )
    

def GetNamespacesFromParsableContent( parsable_content ):
    
    content_type_to_additional_infos = HydrusData.BuildKeyToSetDict( ( ( content_type, additional_infos ) for ( name, content_type, additional_infos ) in parsable_content ) )
    
    namespaces = set( content_type_to_additional_infos[ HC.CONTENT_TYPE_MAPPINGS ] ) # additional_infos is a set of namespaces
    
    if None in namespaces:
        
        namespaces.discard( None )
        
        namespaces.add( '' )
        
    
    namespaces = sorted( namespaces )
    
    return namespaces
    

def GetNamesAndNotesFromParseResults( results ):
    
    name_and_note_results = []
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_NOTES:
            
            note_name = additional_info
            
            note_text = HydrusText.CleanNoteText( parsed_text )
            
            if note_text == '':
                
                continue
                
            
            name_and_note_results.append( ( note_name, parsed_text ) )
            
        
    
    return name_and_note_results
    

def GetSoup( html ):
    
    if HTML5LIB_IS_OK:
        
        parser = 'html5lib'
        
    elif LXML_IS_OK:
        
        parser = 'lxml'
        
    else:
        
        message = 'This client does not have access to either lxml or html5lib, and so it cannot parse html. Please install one of these parsing libraries and restart the client.'
        
        raise HydrusExceptions.ParseException( message )
        
    
    with warnings.catch_warnings():
        
        # bs4 goes bananas with MarkupResemblesLocatorWarning warnings to the log at times, basically when you throw something that looks like a file at it, which I presume sometimes means stuff like '/'
        
        warnings.simplefilter( 'ignore' )
        
        return bs4.BeautifulSoup( html, parser )
        
    

def GetTagsFromParseResults( results ):
    
    tag_results = []
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_MAPPINGS:
            
            namespace = additional_info
            
            make_no_namespace_changes = namespace is None
            
            if make_no_namespace_changes:
                
                combined_tag = parsed_text
                
            else:
                
                combined_tag = HydrusTags.CombineTag( namespace, parsed_text )
                
            
            tag_results.append( combined_tag )
            
        
    
    tag_results = HydrusTags.CleanTags( tag_results )
    
    return tag_results
    

def GetTimestampFromParseResults( results, desired_timestamp_type ):
    
    timestamp_results = []
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_TIMESTAMP:
            
            timestamp_type = additional_info
            
            if timestamp_type == desired_timestamp_type:
                
                try:
                    
                    timestamp = int( parsed_text )
                    
                except:
                    
                    continue
                    
                
                if timestamp_type == HC.TIMESTAMP_TYPE_MODIFIED_DOMAIN:
                    
                    timestamp = min( HydrusTime.GetNow() - 5, timestamp )
                    
                
                timestamp_results.append( timestamp )
                
            
        
    
    if len( timestamp_results ) == 0:
        
        return None
        
    else:
        
        return min( timestamp_results )
        
    

def GetTitleFromAllParseResults( all_parse_results ):
    
    titles = []
    
    for results in all_parse_results:
        
        for ( ( name, content_type, additional_info ), parsed_text ) in results:
            
            if content_type == HC.CONTENT_TYPE_TITLE:
                
                priority = additional_info
                
                titles.append( ( priority, parsed_text ) )
                
            
        
    
    if len( titles ) > 0:
        
        titles.sort( reverse = True ) # highest priority first
        
        ( priority, title ) = titles[0]
        
        return title
        
    else:
        
        return None
        
    

def GetHTTPHeadersFromParseResults( parse_results ):
    
    headers = {}
    
    for ( ( name, content_type, additional_info ), parsed_text ) in parse_results:
        
        if content_type == HC.CONTENT_TYPE_HTTP_HEADERS:
            
            header_name = additional_info
            
            headers[ header_name ] = parsed_text
            
        
    
    return headers
    

def GetURLsFromParseResults( results, desired_url_types, only_get_top_priority = False ):
    
    url_results = collections.defaultdict( list )
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_URLS:
            
            ( url_type, priority ) = additional_info
            
            if url_type in desired_url_types:
                
                url_results[ priority ].append( parsed_text )
                
            
        
    
    if only_get_top_priority:
        
        # ( priority, url_list ) pairs
        
        url_results = list( url_results.items() )
        
        # ordered by descending priority
        
        url_results.sort( reverse = True )
        
        # url_lists of descending priority
        
        if len( url_results ) > 0:
            
            ( priority, url_list ) = url_results[0]
            
        else:
            
            url_list = []
            
        
    else:
        
        url_list = []
        
        for u_l in list(url_results.values()):
            
            url_list.extend( u_l )
            
        
    
    url_list = HydrusData.DedupeList( url_list )
    
    return url_list
    

def GetVariableFromParseResults( results ):
    
    timestamp_results = []
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_VARIABLE:
            
            variable_name = additional_info
            
            return ( variable_name, parsed_text )
            
        
    
    return None
    

def MakeParsedTextPretty( parsed_text ):
    
    if isinstance( parsed_text, bytes ):
        
        return repr( parsed_text )
        
    
    return parsed_text
    

def ParseHashesFromRawHexText( hash_type, hex_hashes_raw ):
    
    hash_type_to_hex_length = {
        'md5' : 32,
        'sha1' : 40,
        'sha256' : 64,
        'sha512' : 128,
        'pixel' : 64,
        'perceptual' : 16
    }
    
    hex_hashes = HydrusText.DeserialiseNewlinedTexts( hex_hashes_raw )
    
    # convert md5:abcd to abcd
    hex_hashes = [ hex_hash.split( ':' )[-1] for hex_hash in hex_hashes ]
    
    hex_hashes = [ HydrusText.HexFilter( hex_hash ) for hex_hash in hex_hashes ]
    
    expected_hex_length = hash_type_to_hex_length[ hash_type ]
    
    bad_hex_hashes = [ hex_hash for hex_hash in hex_hashes if len( hex_hash ) != expected_hex_length ]
    
    if len( bad_hex_hashes ):
        
        m = 'Sorry, {} hashes should have {} hex characters! These did not:'.format( hash_type, expected_hex_length )
        m += '\n' * 2
        m += '\n'.join( ( '{} ({} characters)'.format( bad_hex_hash, len( bad_hex_hash ) ) for bad_hex_hash in bad_hex_hashes ) )
        
        raise Exception( m )
        
    
    hex_hashes = [ hex_hash for hex_hash in hex_hashes if len( hex_hash ) % 2 == 0 ]
    
    hex_hashes = HydrusData.DedupeList( hex_hashes )
    
    hashes = tuple( [ bytes.fromhex( hex_hash ) for hex_hash in hex_hashes ] )
    
    return hashes
    

def ParseResultsHavePursuableURLs( results ):
    
    for ( ( name, content_type, additional_info ), parsed_text ) in results:
        
        if content_type == HC.CONTENT_TYPE_URLS:
            
            ( url_type, priority ) = additional_info
            
            if url_type == HC.URL_TYPE_DESIRED:
                
                return True
                
            
        
    
    return False
    

def RenderJSONParseRule( rule ):
    
    ( parse_rule_type, parse_rule ) = rule
    
    if parse_rule_type == JSON_PARSE_RULE_TYPE_ALL_ITEMS:
        
        s = 'get all items'
        
    elif parse_rule_type == JSON_PARSE_RULE_TYPE_INDEXED_ITEM:
        
        index = parse_rule
        
        s = 'get the ' + HydrusNumbers.IndexToPrettyOrdinalString( index ) + ' item (for Objects, keys sorted)'
        
    elif parse_rule_type == JSON_PARSE_RULE_TYPE_DICT_KEY:
        
        s = 'get the entries that match "' + parse_rule.ToString() + '"'
        
    elif parse_rule_type == JSON_PARSE_RULE_TYPE_DEMINIFY_JSON:
        
        index = parse_rule
        
        s = 'de-minify json at the ' + HydrusNumbers.IndexToPrettyOrdinalString( index ) + ' item'
        
    
    return s
    

class ParsingTestData( object ):
    
    def __init__( self, parsing_context, texts ):
        
        self.parsing_context = parsing_context
        self.texts = texts
        
    
    def LooksLikeHTML( self ):
        
        return True in ( HydrusText.LooksLikeHTML( text ) for text in self.texts )
        
    
    def LooksLikeJSON( self ):
        
        return True in ( HydrusText.LooksLikeJSON( text ) for text in self.texts )
        
    

class ParseFormula( HydrusSerialisable.SerialisableBase ):
    
    def __init__( self, name = None, string_processor = None ):
        
        if name is None:
            
            name = ''
            
        
        if string_processor is None:
            
            string_processor = ClientStrings.StringProcessor()
            
        
        self._name = name
        self._string_processor = string_processor
        
    
    def _GetSerialisableInfo( self ):
        
        raise NotImplementedError()
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        raise NotImplementedError()
        
    
    def _GetParsePrettySeparator( self ):
        
        return '\n'
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text, collapse_newlines: bool ):
        
        raise NotImplementedError()
        
    
    def GetName( self ):
        
        return self._name
        
    
    def GetStringProcessor( self ):
        
        return self._string_processor
        
    
    def Parse( self, parsing_context, parsing_text: str, collapse_newlines: bool ):
        
        raw_texts = self._ParseRawTexts( parsing_context, parsing_text, collapse_newlines )
        
        raw_texts = HydrusText.CleanseImportTexts( raw_texts )
        
        if collapse_newlines:
            
            # maybe should use HydrusText.DeserialiseNewlinedTexts, but that might change/break some existing parsers with the strip() trim
            raw_texts = [ HydrusText.RemoveNewlines( raw_text ) for raw_text in raw_texts ]
            
        else:
            
            # note this does get rid of leading/trailing newlines, which is fine!
            raw_texts = [ raw_text.strip() for raw_text in raw_texts ]
            
        
        texts = self._string_processor.ProcessStrings( raw_texts )
        
        return texts
        
    
    def ParsePretty( self, parsing_context, parsing_text: str, collapse_newlines: bool ):
        
        texts = self.Parse( parsing_context, parsing_text, collapse_newlines )
        
        pretty_texts = [ MakeParsedTextPretty( text ) for text in texts ]
        
        pretty_texts = [ '*** ' + HydrusNumbers.ToHumanInt( len( pretty_texts ) ) + ' RESULTS BEGIN ***' ] + pretty_texts + [ '*** RESULTS END ***' ]
        
        separator = self._GetParsePrettySeparator()
        
        result = separator.join( pretty_texts )
        
        return result
        
    
    def ParsesSeparatedContent( self ):
        
        return False
        
    
    def SetName( self, name: str ):
        
        self._name = name
        
    
    def SetStringProcessor( self, string_processor: "ClientStrings.StringProcessor" ):
        
        self._string_processor = string_processor
        
    
    def ToPrettyString( self ):
        
        raise NotImplementedError()
        
    
    def ToPrettyMultilineString( self ):
        
        raise NotImplementedError()
        
    

class ParseFormulaZipper( ParseFormula ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_ZIPPER
    SERIALISABLE_NAME = 'Zipper Parsing Formula'
    SERIALISABLE_VERSION = 3
    
    def __init__( self, formulae = None, sub_phrase = None, name = None, string_processor = None ):
        
        super().__init__( name = name, string_processor = string_processor )
        
        if formulae is None:
            
            formulae = HydrusSerialisable.SerialisableList()
            
            formulae.append( ParseFormulaHTML() )
            
        
        if sub_phrase is None:
            
            sub_phrase = '\\1'
            
        
        self._formulae = formulae
        
        self._sub_phrase = sub_phrase
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_formulae = HydrusSerialisable.SerialisableList( self._formulae ).GetSerialisableTuple()
        serialisable_string_processor = self._string_processor.GetSerialisableTuple()
        
        return ( serialisable_formulae, self._sub_phrase, self._name, serialisable_string_processor )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_formulae, self._sub_phrase, self._name, serialisable_string_processor ) = serialisable_info
        
        self._formulae = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formulae )
        self._string_processor = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_processor )
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text: str, collapse_newlines: bool ):
        
        def get_stream_string( index, s ):
            
            if len( s ) == 0:
                
                return ''
                
            elif index >= len( s ):
                
                return s[-1]
                
            else:
                
                return s[ index ]
                
            
        
        streams = []
        
        for formula in self._formulae:
            
            stream = formula.Parse( parsing_context, parsing_text, collapse_newlines )
            
            if len( stream ) == 0: # no contents were found for one of the /1 replace components, so no valid strings can be made.
                
                return []
                
            
            streams.append( stream )
            
        
        # let's make a text result for every item in the longest list of subtexts
        num_raw_texts_to_make = max( ( len( stream ) for stream in streams ) )
        
        raw_texts = []
        
        for stream_index in range( num_raw_texts_to_make ):
            
            raw_text = self._sub_phrase
            
            for ( stream_num, stream ) in enumerate( streams, 1 ): # starts counting from 1
                
                sub_component = '\\' + str( stream_num )
                
                replace_string = get_stream_string( stream_index, stream )
                
                raw_text = raw_text.replace( sub_component, replace_string )
                
            
            raw_texts.append( raw_text )
            
        
        return raw_texts
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( serialisable_formulae, sub_phrase, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match )
            string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_converter )
            
            processing_steps = [ processing_step for processing_step in ( string_match, string_converter ) if processing_step.MakesChanges() ]
            
            string_processor = ClientStrings.StringProcessor()
            
            string_processor.SetProcessingSteps( processing_steps )
            
            serialisable_string_processor = string_processor.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_formulae, sub_phrase, serialisable_string_processor )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( serialisable_formulae, sub_phrase, serialisable_string_processor ) = old_serialisable_info
            
            name = ''
            
            new_serialisable_info = ( serialisable_formulae, sub_phrase, name, serialisable_string_processor )
            
            return ( 3, new_serialisable_info )
            
        
    
    def GetFormulae( self ):
        
        return self._formulae
        
    
    def GetSubstitutionPhrase( self ):
        
        return self._sub_phrase
        
    
    def ToPrettyString( self ):
        
        if self._name == '':
            
            t = ''
            
        else:
            
            t = f'{self._name}: '
            
        
        return f'ZIPPER: {t}with {HydrusNumbers.ToHumanInt( len( self._formulae ) )} formulae.'
        
    
    def ToPrettyMultilineString( self ):
        
        s = []
        
        header = '--ZIPPER--'
        
        if self._name != '':
            
            header += '\n' + self._name
            
        
        for formula in self._formulae:
            
            s.append( formula.ToPrettyMultilineString() )
            
        
        s.append( 'and substitute into ' + self._sub_phrase )
        
        separator = '\n' * 2
        
        text = header + '\n' * 2 + separator.join( s )
        
        return text
        
    

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_ZIPPER ] = ParseFormulaZipper

class ParseFormulaContextVariable( ParseFormula ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_CONTEXT_VARIABLE
    SERIALISABLE_NAME = 'Context Variable Formula'
    SERIALISABLE_VERSION = 3
    
    def __init__( self, variable_name = None, name = None, string_processor = None ):
        
        super().__init__( name = name, string_processor = string_processor )
        
        if variable_name is None:
            
            variable_name = 'url'
            
        
        self._variable_name = variable_name
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_string_processor = self._string_processor.GetSerialisableTuple()
        
        return ( self._variable_name, self._name, serialisable_string_processor )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._variable_name, self._name, serialisable_string_processor ) = serialisable_info
        
        self._string_processor = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_processor )
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text, collapse_newlines: bool ):
        
        raw_texts = []
        
        if self._variable_name in parsing_context:
            
            raw_texts.append( str( parsing_context[ self._variable_name ] ) )
            
        
        return raw_texts
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( variable_name, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match )
            string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_converter )
            
            processing_steps = [ processing_step for processing_step in ( string_match, string_converter ) if processing_step.MakesChanges() ]
            
            string_processor = ClientStrings.StringProcessor()
            
            string_processor.SetProcessingSteps( processing_steps )
            
            serialisable_string_processor = string_processor.GetSerialisableTuple()
            
            new_serialisable_info = ( variable_name, serialisable_string_processor )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( variable_name, serialisable_string_processor ) = old_serialisable_info
            
            name = ''
            
            new_serialisable_info = ( variable_name, name, serialisable_string_processor )
            
            return ( 3, new_serialisable_info )
            
        
    
    def GetVariableName( self ):
        
        return self._variable_name
        
    
    def ToPrettyString( self ):
        
        if self._name == '':
            
            t = ''
            
        else:
            
            t = f'{self._name}: '
            
        
        return f'CONTEXT VARIABLE: {t}{self._variable_name}'
        
    
    def ToPrettyMultilineString( self ):
        
        s = []
        
        header = '--CONTEXT VARIABLE--'
        
        if self._name != '':
            
            header += '\n' + self._name
            
        
        s.append( 'fetch the "' + self._variable_name + '" variable from the parsing context' )
        
        separator = '\n' * 2
        
        text = header + '\n' * 2 + separator.join( s )
        
        return text
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_CONTEXT_VARIABLE ] = ParseFormulaContextVariable

HTML_CONTENT_ATTRIBUTE = 0
HTML_CONTENT_STRING = 1
HTML_CONTENT_HTML = 2

class ParseFormulaHTML( ParseFormula ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_HTML
    SERIALISABLE_NAME = 'HTML Parsing Formula'
    SERIALISABLE_VERSION = 8
    
    def __init__( self, tag_rules = None, content_to_fetch = None, attribute_to_fetch = None, name = None, string_processor = None ):
        
        super().__init__( name = name, string_processor = string_processor )
        
        if tag_rules is None:
            
            tag_rules = HydrusSerialisable.SerialisableList()
            
            tag_rules.append( ParseRuleHTML() )
            
        
        if content_to_fetch is None:
            
            content_to_fetch = HTML_CONTENT_ATTRIBUTE
            
        
        if attribute_to_fetch is None:
            
            attribute_to_fetch = 'href'
            
        
        self._tag_rules = HydrusSerialisable.SerialisableList( tag_rules )
        
        self._content_to_fetch = content_to_fetch
        
        self._attribute_to_fetch = attribute_to_fetch
        
    
    def _FindHTMLTags( self, root ):
        
        tags = ( root, )
        
        for tag_rule in self._tag_rules:
            
            tags = list( tag_rule.GetNodes( tags ) )
            
        
        return tags
        
    
    def _GetParsePrettySeparator( self ):
        
        if self._content_to_fetch == HTML_CONTENT_HTML:
            
            return '\n' * 2
            
        else:
            
            return '\n'
            
        
    
    def _GetRawTextFromTag( self, tag ):
        
        if tag is None:
            
            result = None
            
        elif self._content_to_fetch == HTML_CONTENT_ATTRIBUTE:
            
            if tag.has_attr( self._attribute_to_fetch ):
                
                unknown_attr_result = tag[ self._attribute_to_fetch ]
                
                # 'class' attr returns a list because it has multiple values under html spec, wew
                if isinstance( unknown_attr_result, list ):
                    
                    if len( unknown_attr_result ) == 0:
                        
                        raise HydrusExceptions.ParseException( 'Attribute ' + self._attribute_to_fetch + ' not found!' )
                        
                    else:
                        
                        result = ' '.join( unknown_attr_result )
                        
                    
                else:
                    
                    result = unknown_attr_result
                    
                
            else:
                
                raise HydrusExceptions.ParseException( 'Attribute ' + self._attribute_to_fetch + ' not found!' )
                
            
        elif self._content_to_fetch == HTML_CONTENT_STRING:
            
            result = GetHTMLTagString( tag )
            
        elif self._content_to_fetch == HTML_CONTENT_HTML:
            
            result = str( tag )
            
        
        if result is None or result == '':
            
            raise HydrusExceptions.ParseException( 'Empty/No results found!' )
            
        
        return result
        
    
    def _GetRawTextsFromTags( self, tags ):
        
        raw_texts = []
        
        for tag in tags:
            
            try:
                
                raw_text = self._GetRawTextFromTag( tag )
                
                raw_texts.append( raw_text )
                
            except HydrusExceptions.ParseException:
                
                continue
                
            
        
        return raw_texts
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_tag_rules = self._tag_rules.GetSerialisableTuple()
        
        serialisable_string_processor = self._string_processor.GetSerialisableTuple()
        
        return ( serialisable_tag_rules, self._content_to_fetch, self._attribute_to_fetch, self._name, serialisable_string_processor )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_tag_rules, self._content_to_fetch, self._attribute_to_fetch, self._name, serialisable_string_processor ) = serialisable_info
        
        self._tag_rules = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_tag_rules )
        
        self._string_processor = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_processor )
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text, collapse_newlines: bool ):
        
        try:
            
            root = CG.client_controller.parsing_cache.GetSoup( parsing_text )
            
        except Exception as e:
            
            raise HydrusExceptions.ParseException( 'Unable to parse that HTML: {}. HTML Sample: {}'.format( repr( e ), parsing_text[:1024] ) )
            
        
        tags = self._FindHTMLTags( root )
        
        raw_texts = self._GetRawTextsFromTags( tags )
        
        return raw_texts
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( tag_rules, attribute_to_fetch ) = old_serialisable_info
            
            culling_and_adding = ( 0, 0, '', '' )
            
            new_serialisable_info = ( tag_rules, attribute_to_fetch, culling_and_adding )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( tag_rules, attribute_to_fetch, culling_and_adding ) = old_serialisable_info
            
            ( cull_front, cull_back, prepend, append ) = culling_and_adding
            
            conversions = []
            
            if cull_front > 0:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_CLIP_TEXT_FROM_BEGINNING, cull_front ) )
                
            elif cull_front < 0:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_REMOVE_TEXT_FROM_END, cull_front ) )
                
            
            if cull_back > 0:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_CLIP_TEXT_FROM_END, cull_back ) )
                
            elif cull_back < 0:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_REMOVE_TEXT_FROM_BEGINNING, cull_back ) )
                
            
            if prepend != '':
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_PREPEND_TEXT, prepend ) )
                
            
            if append != '':
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_APPEND_TEXT, append ) )
                
            
            string_converter = ClientStrings.StringConverter( conversions, 'parsed information' )
            
            serialisable_string_converter = string_converter.GetSerialisableTuple()
            
            new_serialisable_info = ( tag_rules, attribute_to_fetch, serialisable_string_converter )
            
            return ( 3, new_serialisable_info )
            
        
        if version == 3:
            
            ( tag_rules, attribute_to_fetch, serialisable_string_converter ) = old_serialisable_info
            
            string_match = ClientStrings.StringMatch()
            
            serialisable_string_match = string_match.GetSerialisableTuple()
            
            new_serialisable_info = ( tag_rules, attribute_to_fetch, serialisable_string_match, serialisable_string_converter )
            
            return ( 4, new_serialisable_info )
            
        
        if version == 4:
            
            ( tag_rules, attribute_to_fetch, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            if attribute_to_fetch is None:
                
                content_to_fetch = HTML_CONTENT_STRING
                attribute_to_fetch = ''
                
            else:
                
                content_to_fetch = HTML_CONTENT_ATTRIBUTE
                
            
            new_serialisable_info = ( tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_match, serialisable_string_converter )
            
            return ( 5, new_serialisable_info )
            
        
        if version == 5:
            
            ( tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            new_tag_rules = HydrusSerialisable.SerialisableList()
            
            for ( name, attrs, index ) in tag_rules:
                
                tag_rule = ParseRuleHTML( rule_type = HTML_RULE_TYPE_DESCENDING, tag_name = name, tag_attributes = attrs, tag_index = index )
                
                new_tag_rules.append( tag_rule )
                
            
            serialisable_new_tag_rules = new_tag_rules.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_new_tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_match, serialisable_string_converter )
            
            return ( 6, new_serialisable_info )
            
        
        if version == 6:
            
            ( serialisable_new_tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match )
            string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_converter )
            
            processing_steps = [ processing_step for processing_step in ( string_match, string_converter ) if processing_step.MakesChanges() ]
            
            string_processor = ClientStrings.StringProcessor()
            
            string_processor.SetProcessingSteps( processing_steps )
            
            serialisable_string_processor = string_processor.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_new_tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_processor )
            
            return ( 7, new_serialisable_info )
            
        
        if version == 7:
            
            ( serialisable_new_tag_rules, content_to_fetch, attribute_to_fetch, serialisable_string_processor ) = old_serialisable_info
            
            name = ''
            
            new_serialisable_info = ( serialisable_new_tag_rules, content_to_fetch, attribute_to_fetch, name, serialisable_string_processor )
            
            return ( 8, new_serialisable_info )
            
        
    
    def GetAttributeToFetch( self ):
        
        return self._attribute_to_fetch
        
    
    def GetContentToFetch( self ):
        
        return self._content_to_fetch
        
    
    def GetTagRules( self ):
        
        return self._tag_rules
        
    
    def ParsesSeparatedContent( self ):
        
        return self._content_to_fetch == HTML_CONTENT_HTML
        
    
    def ToPrettyString( self ):
        
        if self._name == '':
            
            t = ''
            
        else:
            
            t = f'{self._name}: '
            
        
        return f'HTML: {t}with {HydrusNumbers.ToHumanInt( len( self._tag_rules ) )} tag rules.'
        
    
    def ToPrettyMultilineString( self ):
        
        pretty_strings = []
        
        header = '--HTML--'
        
        if self._name != '':
            
            header += '\n' + self._name
            
        
        pretty_strings.extend( [ t_r.ToString() for t_r in self._tag_rules ] )
        
        if self._content_to_fetch == HTML_CONTENT_ATTRIBUTE:
            
            pretty_strings.append( 'get the ' + self._attribute_to_fetch + ' attribute of those tags' )
            
        elif self._content_to_fetch == HTML_CONTENT_STRING:
            
            pretty_strings.append( 'get the text content of those tags' )
            
        elif self._content_to_fetch == HTML_CONTENT_HTML:
            
            pretty_strings.append( 'get the html of those tags' )
            
        
        pretty_strings.extend( self._string_processor.GetProcessingStrings() )
        
        separator = '\n' + 'and then '
        
        pretty_multiline_string = header + '\n' + separator.join( pretty_strings )
        
        return pretty_multiline_string
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_HTML ] = ParseFormulaHTML

HTML_RULE_TYPE_DESCENDING = 0
HTML_RULE_TYPE_ASCENDING = 1
HTML_RULE_TYPE_NEXT_SIBLINGS = 2
HTML_RULE_TYPE_PREV_SIBLINGS = 3

class ParseRuleHTML( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_RULE_HTML
    SERIALISABLE_NAME = 'HTML Parsing Rule'
    SERIALISABLE_VERSION = 3
    
    def __init__( self, rule_type = None, tag_name = None, tag_attributes = None, tag_index = None, tag_depth = None, should_test_tag_string = False, tag_string_string_match = None ):
        
        super().__init__()
        
        if rule_type is None:
            
            rule_type = HTML_RULE_TYPE_DESCENDING
            
            if tag_name is None:
                
                tag_name = 'a'
                
            
        
        if rule_type in [ HTML_RULE_TYPE_DESCENDING, HTML_RULE_TYPE_NEXT_SIBLINGS, HTML_RULE_TYPE_PREV_SIBLINGS ]:
            
            if tag_attributes is None:
                
                tag_attributes = {}
                
            
        
        elif rule_type == HTML_RULE_TYPE_ASCENDING:
            
            if tag_depth is None:
                
                tag_depth = 1
                
            
        
        if tag_string_string_match is None:
            
            tag_string_string_match = ClientStrings.StringMatch()
            
        
        self._rule_type = rule_type
        self._tag_name = tag_name
        self._tag_attributes = tag_attributes
        self._tag_index = tag_index
        self._tag_depth = tag_depth
        self._should_test_tag_string = should_test_tag_string
        self._tag_string_string_match = tag_string_string_match
        
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_tag_string_string_match = self._tag_string_string_match.GetSerialisableTuple()
        
        return ( self._rule_type, self._tag_name, self._tag_attributes, self._tag_index, self._tag_depth, self._should_test_tag_string, serialisable_tag_string_string_match )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._rule_type, self._tag_name, self._tag_attributes, self._tag_index, self._tag_depth, self._should_test_tag_string, serialisable_tag_string_string_match ) = serialisable_info
        
        self._tag_string_string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_tag_string_string_match )
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( rule_type, tag_name, tag_attributes, tag_index, tag_depth ) = old_serialisable_info
            
            should_test_tag_string = False
            
            tag_string_string_match = ClientStrings.StringMatch()
            
            serialisable_tag_string_string_match = tag_string_string_match.GetSerialisableTuple()
            
            new_serialisable_info = ( rule_type, tag_name, tag_attributes, tag_index, tag_depth, should_test_tag_string, serialisable_tag_string_string_match )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            return ( 3, old_serialisable_info )
            
        
    
    def GetNodes( self, nodes ):
        
        new_nodes = []
        
        for node in nodes:
            
            if self._rule_type in [ HTML_RULE_TYPE_DESCENDING, HTML_RULE_TYPE_NEXT_SIBLINGS, HTML_RULE_TYPE_PREV_SIBLINGS ]:
                
                # having class : [ 'a', 'b' ] works here, but it does OR not AND
                # instead do node.find_all( lambda tag: 'class' in tag.attrs and 'a' in tag[ 'class' ] and 'b' in tag[ 'class' ] )
                # which means we want to just roll all this into one method to support multiple class matching
                
                kwargs = { 'attrs' : self._tag_attributes }
                
                if self._tag_name is not None:
                    
                    kwargs[ 'name' ] = self._tag_name
                    
                
                if self._rule_type == HTML_RULE_TYPE_DESCENDING:
                    
                    found_nodes = node.find_all( **kwargs )
                    
                elif self._rule_type == HTML_RULE_TYPE_NEXT_SIBLINGS:
                    
                    found_nodes = node.find_next_siblings( **kwargs )
                    
                elif self._rule_type == HTML_RULE_TYPE_PREV_SIBLINGS:
                    
                    found_nodes = node.find_previous_siblings( **kwargs )
                    

                if self._tag_index is not None:
                    
                    try:
                        
                        indexed_node = found_nodes[ self._tag_index ]
                        
                    except IndexError:
                        
                        continue
                        
                    
                    found_nodes = [ indexed_node ]
                    
                
            elif self._rule_type == HTML_RULE_TYPE_ASCENDING:
                
                found_nodes = []
                
                still_in_tree = lambda node: isinstance( node, bs4.element.Tag ) # if we go one above html, we get the BS document itself
                
                num_found = 0
                
                potential_parent = node.parent
                
                while still_in_tree( potential_parent ):
                    
                    if self._tag_name is None:
                        
                        num_found += 1
                        
                    else:
                        
                        if potential_parent.name == self._tag_name:
                            
                            num_found += 1
                            
                        
                    
                    if num_found == self._tag_depth:
                        
                        found_nodes = [ potential_parent ]
                        
                        break
                        
                    
                    potential_parent = potential_parent.parent
                    
                
            
            new_nodes.extend( found_nodes )
            
        
        if self._should_test_tag_string:
            
            potential_nodes = new_nodes
            
            new_nodes = []
            
            for node in potential_nodes:
                
                s = GetHTMLTagString( node )
                
                if self._tag_string_string_match.Matches( s ):
                    
                    new_nodes.append( node )
                    
                
            
        
        return new_nodes
        
    
    def ToString( self ):
        
        if self._rule_type in [ HTML_RULE_TYPE_DESCENDING, HTML_RULE_TYPE_NEXT_SIBLINGS, HTML_RULE_TYPE_PREV_SIBLINGS ]:
            
            if self._rule_type == HTML_RULE_TYPE_DESCENDING:
                
                s = 'search descendants for'
                
            elif self._rule_type == HTML_RULE_TYPE_NEXT_SIBLINGS:
                
                s = 'search next siblings for'
                
            elif self._rule_type == HTML_RULE_TYPE_PREV_SIBLINGS:
                
                s = 'search previous siblings for'
                
            if self._tag_index is None:
                
                s += ' every'
                
            else:
                
                s += ' the ' + HydrusNumbers.IndexToPrettyOrdinalString( self._tag_index )
                
            
            if self._tag_name is not None:
                
                s += ' <' + self._tag_name + '>'
                
            
            s += ' tag'
            
            if len( self._tag_attributes ) > 0:
                
                s += ' with attributes ' + ', '.join( key + '=' + value for ( key, value ) in list(self._tag_attributes.items()) )
                
            
        elif self._rule_type == HTML_RULE_TYPE_ASCENDING:
            
            s = 'walk back up ancestors'
            
            if self._tag_name is None:
                
                s += ' ' + HydrusNumbers.ToHumanInt( self._tag_depth ) + ' tag levels'
                
            else:
                
                s += ' to the ' + HydrusNumbers.IntToPrettyOrdinalString( self._tag_depth ) + ' <' + self._tag_name + '> tag'
                
            
        
        if self._should_test_tag_string:
            
            s += ' with strings that match ' + self._tag_string_string_match.ToString()
            
        
        return s
        
    
    def ToTuple( self ):
        
        return ( self._rule_type, self._tag_name, self._tag_attributes, self._tag_index, self._tag_depth, self._should_test_tag_string, self._tag_string_string_match )
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_RULE_HTML ] = ParseRuleHTML

JSON_CONTENT_STRING = 0
JSON_CONTENT_JSON = 1
JSON_CONTENT_DICT_KEYS = 2

JSON_PARSE_RULE_TYPE_DICT_KEY = 0
JSON_PARSE_RULE_TYPE_ALL_ITEMS = 1
JSON_PARSE_RULE_TYPE_INDEXED_ITEM = 2
JSON_PARSE_RULE_TYPE_DEMINIFY_JSON = 3

class ParseFormulaJSON( ParseFormula ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_JSON
    SERIALISABLE_NAME = 'JSON Parsing Formula'
    SERIALISABLE_VERSION = 4
    
    def __init__( self, parse_rules = None, content_to_fetch = None, name = None, string_processor = None ):
        
        super().__init__( name = name, string_processor = string_processor )
        
        if parse_rules is None:
            
            parse_rules = [ ( JSON_PARSE_RULE_TYPE_DICT_KEY, ClientStrings.StringMatch( match_type = ClientStrings.STRING_MATCH_FIXED, match_value = 'posts', example_string = 'posts' ) ) ]
            
        
        if content_to_fetch is None:
            
            content_to_fetch = JSON_CONTENT_STRING
            
        
        self._parse_rules = parse_rules
        
        self._content_to_fetch = content_to_fetch
        
    
    def _GetParsePrettySeparator( self ):
        
        if self._content_to_fetch == JSON_CONTENT_JSON:
            
            return '\n' * 2
            
        else:
            
            return '\n'
            
        
    
    def _GetRawTextsFromJSON( self, j ):
        
        roots = ( j, )
        
        for ( parse_rule_type, parse_rule ) in self._parse_rules:
            
            next_roots = []
            
            for root in roots:
                
                if parse_rule_type == JSON_PARSE_RULE_TYPE_ALL_ITEMS:
                    
                    if isinstance( root, list ):
                        
                        next_roots.extend( root )
                        
                    elif isinstance( root, dict ):
                        
                        pairs = sorted( root.items() )
                        
                        for ( key, value ) in pairs:
                            
                            next_roots.append( value )
                            
                        
                    else:
                        
                        continue
                        
                    
                elif parse_rule_type == JSON_PARSE_RULE_TYPE_INDEXED_ITEM:
                    
                    index = parse_rule
                    
                    if isinstance( root, ( list, dict ) ):
                        
                        if isinstance( root, list ):
                            
                            list_to_index = root
                            
                        elif isinstance( root, dict ):
                            
                            list_to_index = list( root.keys() )
                            
                            HydrusData.HumanTextSort( list_to_index )
                            
                        
                        try:
                            
                            indexed_item = list_to_index[ index ]
                            
                        except IndexError:
                            
                            continue
                            
                        
                        if isinstance( root, list ):
                            
                            next_roots.append( indexed_item )
                            
                        elif isinstance( root, dict ):
                            
                            next_roots.append( root[ indexed_item ] )
                            
                        
                    else:
                        
                        continue
                        
                    
                elif parse_rule_type == JSON_PARSE_RULE_TYPE_DICT_KEY:
                    
                    if not isinstance( root, dict ):
                        
                        continue
                        
                    
                    string_match = parse_rule
                    
                    pairs = sorted( root.items() )
                    
                    for ( key, value ) in pairs:
                        
                        if string_match.Matches( key ):
                            
                            next_roots.append( value )
                            
                        
                    
                elif parse_rule_type == JSON_PARSE_RULE_TYPE_DEMINIFY_JSON:
                    
                    if not isinstance( root, list ):
                        
                        continue
                        
                    
                    index = parse_rule
                    
                    def _deminify( item ):
                        """
                        Example:
                            >>> root = [["test", 1], {"key": 2, "value": 3}, 123, "asd"]
                            >>> _deminify(root[0])
                            ["test", {"key": 123, "value": "asd"}]
                        """
                        
                        if isinstance( item, list ):
                            
                            return [ _deminify( i ) for i in item ]
                            
                        elif isinstance( item, dict ):
                            
                            return { k: _deminify( v ) for k, v in item.items() }
                            
                        elif isinstance( item, int ):
                            
                            # Don't convert topmost integer
                            if isinstance( root[ item ], int ):
                                
                                return root[ item ]
                                
                            
                            return _deminify( root[ item ] )
                            
                        else:
                            
                            return item
                            
                        
                    
                    try:
                        
                        next_roots.append( _deminify( root[ index ] ) )
                        
                    except IndexError:
                        
                        continue
                        
                    
                
            
            roots = next_roots
            
        
        raw_texts = []
        
        for root in roots:
            
            if self._content_to_fetch == JSON_CONTENT_STRING:
                
                if isinstance( root, ( list, dict ) ):
                    
                    continue
                    
                
                if root is not None:
                    
                    raw_text = str( root )
                    
                    raw_texts.append( raw_text )
                    
                
            elif self._content_to_fetch == JSON_CONTENT_JSON:
                
                raw_text = json.dumps( root, ensure_ascii = False )
                
                raw_texts.append( raw_text )
                
            elif self._content_to_fetch == JSON_CONTENT_DICT_KEYS:
                
                if isinstance( root, dict ):
                    
                    pairs = sorted( root.items() )
                    
                    for ( key, value ) in pairs:
                        
                        raw_text = str( key )
                        
                        raw_texts.append( raw_text )
                        
                    
                
            
        
        return raw_texts
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_parse_rules = [ ( parse_rule_type, parse_rule.GetSerialisableTuple() ) if parse_rule_type == JSON_PARSE_RULE_TYPE_DICT_KEY else ( parse_rule_type, parse_rule ) for ( parse_rule_type, parse_rule ) in self._parse_rules ]
        serialisable_string_processor = self._string_processor.GetSerialisableTuple()
        
        return ( serialisable_parse_rules, self._content_to_fetch, self._name, serialisable_string_processor )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_parse_rules, self._content_to_fetch, self._name, serialisable_string_processor ) = serialisable_info
        
        self._parse_rules = [ ( parse_rule_type, HydrusSerialisable.CreateFromSerialisableTuple( serialisable_parse_rule ) ) if parse_rule_type == JSON_PARSE_RULE_TYPE_DICT_KEY else ( parse_rule_type, serialisable_parse_rule ) for ( parse_rule_type, serialisable_parse_rule ) in serialisable_parse_rules ]
        self._string_processor = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_processor )
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text, collapse_newlines: bool ):
        
        try:
            
            j = CG.client_controller.parsing_cache.GetJSON( parsing_text )
            
        except Exception as e:
            
            if HydrusText.LooksLikeHTML( parsing_text ):
                
                message = 'Unable to parse: Appeared to receive HTML instead of JSON.'
                
            else:
                
                message = 'Unable to parse that JSON: {}.'.format( repr( e ) )
                
            
            message += ' Parsing text sample: {}'.format( parsing_text[:1024] )
            
            raise HydrusExceptions.ParseException( message )
            
        
        raw_texts = self._GetRawTextsFromJSON( j )
        
        return raw_texts
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( parse_rules, content_to_fetch, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            new_parse_rules = []
            
            for parse_rule in parse_rules:
                
                if parse_rule is None:
                    
                    new_parse_rules.append( ( JSON_PARSE_RULE_TYPE_ALL_ITEMS, None ) )
                    
                elif isinstance( parse_rule, int ):
                    
                    new_parse_rules.append( ( JSON_PARSE_RULE_TYPE_INDEXED_ITEM, parse_rule ) )
                    
                else:
                    
                    sm = ClientStrings.StringMatch( match_type = ClientStrings.STRING_MATCH_FIXED, match_value = parse_rule, example_string = parse_rule )
                    
                    new_parse_rules.append( ( JSON_PARSE_RULE_TYPE_DICT_KEY, sm ) )
                    
                
            
            serialisable_parse_rules = [ ( parse_rule_type, parse_rule.GetSerialisableTuple() ) if parse_rule_type == JSON_PARSE_RULE_TYPE_DICT_KEY else ( parse_rule_type, parse_rule ) for ( parse_rule_type, parse_rule ) in new_parse_rules ]
            
            new_serialisable_info = ( serialisable_parse_rules, content_to_fetch, serialisable_string_match, serialisable_string_converter )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( serialisable_parse_rules, content_to_fetch, serialisable_string_match, serialisable_string_converter ) = old_serialisable_info
            
            string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match )
            string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_converter )
            
            processing_steps = [ processing_step for processing_step in ( string_match, string_converter ) if processing_step.MakesChanges() ]
            
            string_processor = ClientStrings.StringProcessor()
            
            string_processor.SetProcessingSteps( processing_steps )
            
            serialisable_string_processor = string_processor.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_parse_rules, content_to_fetch, serialisable_string_processor )
            
            return ( 3, new_serialisable_info )
            
        
        if version == 3:
            
            ( serialisable_parse_rules, content_to_fetch, serialisable_string_processor ) = old_serialisable_info
            
            name = ''
            
            new_serialisable_info = ( serialisable_parse_rules, content_to_fetch, name, serialisable_string_processor )
            
            return ( 4, new_serialisable_info )
            
        
    
    def GetContentToFetch( self ):
        
        return self._content_to_fetch
        
    
    def GetParseRules( self ):
        
        return self._parse_rules
        
    
    def ParsesSeparatedContent( self ):
        
        return self._content_to_fetch == JSON_CONTENT_JSON
        
    
    def ToPrettyString( self ):
        
        if self._name == '':
            
            t = ''
            
        else:
            
            t = f'{self._name}: '
            
        
        return f'JSON: {t}with {HydrusNumbers.ToHumanInt( len( self._parse_rules ) )} parse rules.'
        
    
    def ToPrettyMultilineString( self ):
        
        header = '--JSON--'
        
        if self._name != '':
            
            header += '\n' + self._name
            
        
        pretty_strings = [ RenderJSONParseRule( p_r ) for p_r in self._parse_rules ]
        
        if self._content_to_fetch == JSON_CONTENT_STRING:
            
            pretty_strings.append( 'get final data content, converting to strings as needed' )
            
        elif self._content_to_fetch == JSON_CONTENT_JSON:
            
            pretty_strings.append( 'get the json beneath' )
            
        elif self._content_to_fetch == JSON_CONTENT_DICT_KEYS:
            
            pretty_strings.append( 'get the dictionary keys' )
            
        
        pretty_strings.extend( self._string_processor.GetProcessingStrings() )
        
        separator = '\n' + 'and then '
        
        pretty_multiline_string = header + '\n' + separator.join( pretty_strings )
        
        return pretty_multiline_string
        
    

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_JSON ] = ParseFormulaJSON

class ParseFormulaNested( ParseFormula ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_NESTED
    SERIALISABLE_NAME = 'Nested Parsing Formula'
    SERIALISABLE_VERSION = 2
    
    def __init__( self, main_formula = None, sub_formula = None, name = None, string_processor = None ):
        
        super().__init__( name = name, string_processor = string_processor )
        
        if main_formula is None:
            
            main_formula = ParseFormulaHTML()
            
        
        if sub_formula is None:
            
            sub_formula = ParseFormulaJSON()
            
        
        self._main_formula = main_formula
        self._sub_formula = sub_formula
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_main_formula = self._main_formula.GetSerialisableTuple()
        serialisable_sub_formula = self._sub_formula.GetSerialisableTuple()
        serialisable_string_processor = self._string_processor.GetSerialisableTuple()
        
        return ( serialisable_main_formula, serialisable_sub_formula, self._name, serialisable_string_processor )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_main_formula, serialisable_sub_formula, self._name, serialisable_string_processor ) = serialisable_info
        
        self._main_formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_main_formula )
        self._sub_formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_sub_formula )
        self._string_processor = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_processor )
        
    
    def _ParseRawTexts( self, parsing_context, parsing_text: str, collapse_newlines: bool ):
        
        all_sub_parsed_texts = []
        
        main_parsed_texts = self._main_formula.Parse( parsing_context, parsing_text, collapse_newlines )
        
        for main_parsed_text in main_parsed_texts:
            
            sub_parsed_texts = self._sub_formula.Parse( parsing_context, main_parsed_text, collapse_newlines )
            
            all_sub_parsed_texts.extend( sub_parsed_texts )
            
        
        return all_sub_parsed_texts
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( serialisable_main_formula, serialisable_sub_formula, serialisable_string_processor ) = old_serialisable_info
            
            name = ''
            
            new_serialisable_info = ( serialisable_main_formula, serialisable_sub_formula, name, serialisable_string_processor )
            
            return ( 2, new_serialisable_info )
            
        
    
    def GetMainFormula( self ):
        
        return self._main_formula
        
    
    def GetSubFormula( self ):
        
        return self._sub_formula
        
    
    def ToPrettyString( self ):
        
        if self._name == '':
            
            t = ''
            
        else:
            
            t = f'{self._name}: '
            
        
        return f'NESTED formulae: {t}taking from "{self._main_formula.ToPrettyString()}" and sending to "{self._sub_formula.ToPrettyString()}".'
        
    
    def ToPrettyMultilineString( self ):
        
        header = '--NESTED--'
        
        if self._name != '':
            
            header += '\n' + self._name
            
        
        text = header + '\n' * 2 + self._main_formula.ToPrettyMultilineString() + '\n->\n' + self._sub_formula.ToPrettyMultilineString()
        
        return text
        
    

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_FORMULA_NESTED ] = ParseFormulaNested

class SimpleDownloaderParsingFormula( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_SIMPLE_DOWNLOADER_PARSE_FORMULA
    SERIALISABLE_NAME = 'Simple Downloader Parsing Formula'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, name = None, formula = None ):
        
        if name is None:
            
            name = 'new parsing formula'
            
        
        if formula is None:
            
            formula = ParseFormulaHTML()
            
        
        super().__init__( name )
        
        self._formula = formula
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_formula = self._formula.GetSerialisableTuple()
        
        return serialisable_formula
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        serialisable_formula = serialisable_info
        
        self._formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula )
        
    
    def GetFormula( self ):
        
        return self._formula
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_SIMPLE_DOWNLOADER_PARSE_FORMULA ] = SimpleDownloaderParsingFormula

class ContentParser( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_CONTENT_PARSER
    SERIALISABLE_NAME = 'Content Parser'
    SERIALISABLE_VERSION = 7
    
    def __init__( self, name = None, content_type = None, formula = None, additional_info = None ):
        
        if name is None:
            
            name = ''
            
        
        if content_type is None:
            
            content_type = HC.CONTENT_TYPE_MAPPINGS
            
        
        if formula is None:
            
            formula = ParseFormulaHTML()
            
        
        self._name = name
        self._content_type = content_type
        self._formula = formula
        self._additional_info = additional_info
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_formula = self._formula.GetSerialisableTuple()
        
        if self._content_type == HC.CONTENT_TYPE_VETO:
            
            ( veto_if_matches_found, string_match ) = self._additional_info
            
            serialisable_additional_info = ( veto_if_matches_found, string_match.GetSerialisableTuple() )
            
        else:
            
            serialisable_additional_info = self._additional_info
            
        
        return ( self._name, self._content_type, serialisable_formula, serialisable_additional_info )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._name, self._content_type, serialisable_formula, serialisable_additional_info ) = serialisable_info
        
        if self._content_type == HC.CONTENT_TYPE_VETO:
            
            ( veto_if_matches_found, serialisable_string_match ) = serialisable_additional_info
            
            string_match = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match )
            
            self._additional_info = ( veto_if_matches_found, string_match )
            
        else:
            
            self._additional_info = serialisable_additional_info
            
            if isinstance( self._additional_info, list ):
                
                additional_info = []
                
                for item in self._additional_info:
                    
                    # this fixes some garbage accidental update caused by borked version numbers that made ( [ 'md5', 'hex' ], 'hex' )
                    if isinstance( item, list ):
                        
                        additional_info = tuple( item )
                        
                        break
                        
                    
                    additional_info.append( item )
                    
                
                self._additional_info = tuple( additional_info )
                
            
        
        self._formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula )
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( name, content_type, serialisable_formula, additional_info ) = old_serialisable_info
            
            if content_type == HC.CONTENT_TYPE_VETO:
                
                ( veto_if_matches_found, match_if_text_present, search_text ) = additional_info
                
                if match_if_text_present:
                    
                    string_match = ClientStrings.StringMatch( match_type = ClientStrings.STRING_MATCH_REGEX, match_value = search_text, example_string = search_text )
                    
                else:
                    
                    string_match = ClientStrings.StringMatch()
                    
                
                serialisable_string_match = string_match.GetSerialisableTuple()
                
                additional_info = ( veto_if_matches_found, serialisable_string_match )
                
            
            new_serialisable_info = ( name, content_type, serialisable_formula, additional_info )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( name, content_type, serialisable_formula, additional_info ) = old_serialisable_info
            
            if content_type == HC.CONTENT_TYPE_URLS:
                
                ( url_type, priority ) = additional_info
                
                if url_type == HC.URL_TYPE_FILE:
                    
                    url_type = HC.URL_TYPE_DESIRED
                    
                elif url_type == HC.URL_TYPE_POST:
                    
                    url_type = HC.URL_TYPE_SOURCE
                    
                else:
                    
                    url_type = HC.URL_TYPE_NEXT
                    
                
                additional_info = ( url_type, priority )
                
            
            new_serialisable_info = ( name, content_type, serialisable_formula, additional_info )
            
            return ( 3, new_serialisable_info )
            
        
        if version == 3:
            
            ( name, content_type, serialisable_formula, additional_info ) = old_serialisable_info
            
            sort_type = ClientStrings.CONTENT_PARSER_SORT_TYPE_NONE
            sort_asc = False
            
            new_serialisable_info = ( name, content_type, serialisable_formula, sort_type, sort_asc, additional_info )
            
            return ( 4, new_serialisable_info )
            
        
        if version == 4:
            
            ( name, content_type, serialisable_formula, sort_type, sort_asc, additional_info ) = old_serialisable_info
            
            if content_type == HC.CONTENT_TYPE_HASH and not isinstance( additional_info, list ):
                
                hash_encoding = 'hex'
                
                if '"base64"' in json.dumps( serialisable_formula ): # lmao, top code
                    
                    hash_encoding = 'base64'
                    
                
                hash_type = additional_info
                
                additional_info = ( hash_type, hash_encoding )
                
            
            new_serialisable_info = ( name, content_type, serialisable_formula, sort_type, sort_asc, additional_info )
            
            return ( 5, new_serialisable_info )
            
        
        if version == 5:
            
            ( name, content_type, serialisable_formula, sort_type, sort_asc, additional_info ) = old_serialisable_info
            
            if sort_type != ClientStrings.CONTENT_PARSER_SORT_TYPE_NONE:
                
                formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula )
                
                string_processor = formula.GetStringProcessor()
                
                processing_steps = string_processor.GetProcessingSteps()
                
                processing_steps.append( ClientStrings.StringSorter( sort_type = sort_type, asc = sort_asc ) )
                
                string_processor.SetProcessingSteps( processing_steps )
                
                serialisable_formula = formula.GetSerialisableTuple()
                
            
            new_serialisable_info = ( name, content_type, serialisable_formula, additional_info )
            
            return ( 6, new_serialisable_info )
            
        
        if version == 6:
            
            ( name, content_type, serialisable_formula, additional_info ) = old_serialisable_info
            
            if content_type == HC.CONTENT_TYPE_MAPPINGS:
                
                namespace = additional_info
                
                if namespace == '':
                    
                    namespace = None
                    
                
                additional_info = namespace
                
            
            new_serialisable_info = ( name, content_type, serialisable_formula, additional_info )
            
            return ( 7, new_serialisable_info )
            
        
    
    def GetName( self ):
        
        return self._name
        
    
    def GetParsableContent( self ):
        
        return { ( self._name, self._content_type, self._additional_info ) }
        
    
    def Parse( self, parsing_context, parsing_text ):
        
        try:
            
            collapse_newlines = self._content_type != HC.CONTENT_TYPE_NOTES
            
            parsed_texts = list( self._formula.Parse( parsing_context, parsing_text, collapse_newlines ) )
            
        except HydrusExceptions.ParseException as e:
            
            prefix = 'Content Parser ' + self._name + ': '
            
            e = HydrusExceptions.ParseException( prefix + str( e ) )
            
            raise e
            
        
        if self._content_type == HC.CONTENT_TYPE_NOTES:
            
            parsed_texts = [ HydrusText.CleanNoteText( parsed_text ) for parsed_text in parsed_texts ]
            
        
        if self._content_type == HC.CONTENT_TYPE_URLS:
            
            if 'url' in parsing_context:
                
                base_url = parsing_context[ 'url' ]
                
                def remove_pre_url_gubbins( u ):
                    
                    # clears up when a source field starts with gubbins for some reason. e.g.:
                    # (jap characters).avi | ranken [pixiv] http://www.pixiv.net/member_illust.php?illust_id=48114073&mode=medium
                    # ->
                    # http://www.pixiv.net/member_illust.php?illust_id=48114073&mode=medium
                    
                    gumpf_until_scheme = r'^.*\s(?P<scheme>https?://)'
                    
                    result = re.search( gumpf_until_scheme, u )
                    
                    if result is not None:
                        
                        scheme = result.group( 'scheme' )
                        
                        u = re.sub( gumpf_until_scheme, scheme, u )
                        
                    
                    # http://http://...
                    multiple_schemes_pattern = r'^(?:https?://)+(?P<scheme>https?://)'
                    
                    result = re.search( multiple_schemes_pattern, u )
                    
                    if result is not None:
                        
                        true_scheme = result.group( 'scheme' )
                        
                        u = re.sub( multiple_schemes_pattern, true_scheme, u )
                        
                    
                    return u
                    
                
                clean_urls = []
                
                for unclean_url in parsed_texts:
                    
                    if not ClientNetworkingFunctions.LooksLikeAFullURL( unclean_url ) and ( 'http://' in unclean_url or 'https://' in unclean_url ):
                        
                        unclean_url = remove_pre_url_gubbins( unclean_url )
                        
                    
                    if not ClientNetworkingFunctions.LooksLikeAFullURL( unclean_url ):
                        
                        try:
                            
                            unclean_url = urllib.parse.urljoin( base_url, unclean_url )
                            
                        except:
                            
                            pass # welp
                            
                        
                    
                    clean_url = ClientNetworkingFunctions.EnsureURLIsEncoded( unclean_url )
                    
                    clean_urls.append( clean_url )
                    
                
                parsed_texts = clean_urls
                
            
        
        if self._content_type == HC.CONTENT_TYPE_TITLE:
            
            try:
                
                # handling &amp; gubbins that come through JSON, although the better answer is to convert to an html parser
                parsed_texts = [ html.unescape( parsed_text ) for parsed_text in parsed_texts ]
                
            except:
                
                HydrusData.Print( f'Could not unescape parsed title text: {parsing_context}' )
                
            
        
        if self._content_type == HC.CONTENT_TYPE_VETO:
            
            ( veto_if_matches_found, string_match ) = self._additional_info
            
            match_found = True in ( string_match.Matches( parsed_text ) for parsed_text in parsed_texts )
            
            veto_if_missing = not veto_if_matches_found
            
            do_veto = ( veto_if_matches_found and match_found ) or ( veto_if_missing and not match_found )
            
            if do_veto:
                
                raise HydrusExceptions.VetoException( 'veto: {}'.format( self._name ) )
                
            else:
                
                return []
                
            
        else:
            
            content_description = ( self._name, self._content_type, self._additional_info )
            
            return [ ( content_description, parsed_text ) for parsed_text in parsed_texts ]
            
        
    
    def ParsePretty( self, parsing_context, parsing_text: str ):
        
        try:
            
            parse_results = self.Parse( parsing_context, parsing_text )
            
            results = [ ConvertParseResultToPrettyString( parse_result ) for parse_result in parse_results ]
            
        except HydrusExceptions.VetoException as e:
            
            results = [ 'veto: ' + str( e ) ]
            
        except HydrusExceptions.ParseException as e:
            
            prefix = 'Content Parser ' + self._name + ': '
            
            e = HydrusExceptions.ParseException( prefix + str( e ) )
            
            raise e
            
        
        result_lines = [ '*** ' + HydrusNumbers.ToHumanInt( len( results ) ) + ' RESULTS BEGIN ***' ]
        
        result_lines.extend( results )
        
        result_lines.append( '*** RESULTS END ***' )
        
        results_text = '\n'.join( result_lines )
        
        return results_text
        
    
    def SetName( self, name ):
        
        self._name = name
        
    
    def ToPrettyStrings( self ):
        
        return ( self._name, 'content', ConvertParsableContentToPrettyString( self.GetParsableContent(), include_veto = True ) )
        
    
    def ToTuple( self ):
        
        return ( self._name, self._content_type, self._formula, self._additional_info )
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_CONTENT_PARSER ] = ContentParser

class PageParser( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PAGE_PARSER
    SERIALISABLE_NAME = 'Page Parser'
    SERIALISABLE_VERSION = 3
    
    def __init__( self, name, parser_key = None, string_converter = None, sub_page_parsers = None, content_parsers = None, example_urls = None, example_parsing_context = None ):
        
        if parser_key is None:
            
            parser_key = HydrusData.GenerateKey()
            
        
        if string_converter is None:
            
            string_converter = ClientStrings.StringConverter()
            
        
        if sub_page_parsers is None:
            
            sub_page_parsers = []
            
        
        if content_parsers is None:
            
            content_parsers = []
            
        
        if example_urls is None:
            
            example_urls = []
            
        
        if example_parsing_context is None:
            
            example_parsing_context = {}
            
            example_parsing_context[ 'url' ] = 'https://example.com/posts/index.php?id=123456'
            
        
        super().__init__( name )
        
        self._parser_key: bytes = parser_key
        self._string_converter: ClientStrings.StringConverter = string_converter
        self._sub_page_parsers: typing.List[ SubsidiaryPageParser ] = sub_page_parsers
        self._content_parsers: typing.List[ ContentParser ] = content_parsers
        self._example_urls: typing.Collection[ str ] = example_urls
        self._example_parsing_context: dict = example_parsing_context
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_parser_key = self._parser_key.hex()
        serialisable_string_converter = self._string_converter.GetSerialisableTuple()
        
        serialisable_sub_page_parsers = HydrusSerialisable.SerialisableList( sorted( self._sub_page_parsers, key = lambda spp: spp.GetPageParser().GetName().casefold() ) ).GetSerialisableTuple()
        
        serialisable_content_parsers = HydrusSerialisable.SerialisableList( sorted( self._content_parsers, key = lambda p: p.GetName().casefold() ) ).GetSerialisableTuple()
        
        return ( self._name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, self._example_urls, self._example_parsing_context )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, self._example_urls, self._example_parsing_context ) = serialisable_info
        
        self._parser_key = bytes.fromhex( serialisable_parser_key )
        self._string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_converter )
        self._sub_page_parsers = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_sub_page_parsers )
        self._content_parsers = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_content_parsers )
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, example_urls ) = old_serialisable_info
            
            example_parsing_context = {}
            
            example_parsing_context[ 'url' ] = 'https://example.com/posts/index.php?id=123456'
            
            new_serialisable_info = ( name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, example_urls, example_parsing_context )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, example_urls, example_parsing_context ) = old_serialisable_info
            
            old_sub_page_parsers = [ ( HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula ), HydrusSerialisable.CreateFromSerialisableTuple( serialisable_page_parser ) ) for ( serialisable_formula, serialisable_page_parser ) in serialisable_sub_page_parsers ]
            
            sub_page_parsers = HydrusSerialisable.SerialisableList( [ SubsidiaryPageParser( formula = formula, page_parser = page_parser ) for ( formula, page_parser ) in old_sub_page_parsers ] )
            
            serialisable_sub_page_parsers = sub_page_parsers.GetSerialisableTuple()
            
            new_serialisable_info = ( name, serialisable_parser_key, serialisable_string_converter, serialisable_sub_page_parsers, serialisable_content_parsers, example_urls, example_parsing_context )
            
            return ( 3, new_serialisable_info )
            
        
    
    def CanOnlyGenerateGalleryURLs( self ):
        
        can_generate_gallery_urls = False
        can_generate_other_urls = False
        
        parsable_content = self.GetParsableContent()
        
        for ( name, content_type, additional_info ) in parsable_content:
            
            if content_type == HC.CONTENT_TYPE_URLS:
                
                ( url_type, priority ) = additional_info
                
                if url_type == HC.URL_TYPE_GALLERY:
                    
                    can_generate_gallery_urls = True
                    
                else:
                    
                    can_generate_other_urls = True
                    
                
            
        
        return can_generate_gallery_urls and not can_generate_other_urls
        
    
    def GetContentParsers( self ):
        
        return ( self._sub_page_parsers, self._content_parsers )
        
    
    def GetExampleParsingContext( self ):
        
        return self._example_parsing_context
        
    
    def GetExampleURLs( self, encoded = True ):
        
        if encoded:
            
            return [ ClientNetworkingFunctions.EnsureURLIsEncoded( url ) for url in self._example_urls ]
            
        else:
            
            return list( self._example_urls )
            
        
    
    def GetNamespaces( self ):
        
        # this in future could expand to be more granular like:
        # 'I want the artist tags, but not the user-submitted.'
        # 'I want the title here, but not the title there.'
        # 'I want the original filename, but not the UNIX timestamp filename.'
        # which the parser could present with its sub-parsing element names
        
        return GetNamespacesFromParsableContent( self.GetParsableContent() )
        
    
    def GetParsableContent( self ):
        
        parsable_content = set()
        
        for sub_page_parser in self._sub_page_parsers:
            
            parsable_content.update( sub_page_parser.GetPageParser().GetParsableContent() )
            
        
        for content_parser in self._content_parsers:
            
            parsable_content.update( content_parser.GetParsableContent() )
            
        
        return parsable_content
        
    
    def GetParserKey( self ):
        
        return self._parser_key
        
    
    def GetSafeSummary( self ):
        
        domains = sorted( { ClientNetworkingFunctions.ConvertURLIntoDomain( url ) for url in self._example_urls } )
        
        return 'Parser "' + self._name + '" - ' + ', '.join( domains )
        
    
    def GetStringConverter( self ):
        
        return self._string_converter
        
    
    def NullifyTestData( self ):
        
        self._example_parsing_context = {}
        
        for sub_page_parser in self._sub_page_parsers:
            
            sub_page_parser.GetPageParser().NullifyTestData()
            
        
    
    def Parse( self, parsing_context, parsing_text ):
        
        try:
            
            converted_parsing_text = self._string_converter.Convert( parsing_text )
            
        except HydrusExceptions.StringConvertException as e:
            
            raise HydrusExceptions.ParseException( str( e ) )
            
        except HydrusExceptions.ParseException as e:
            
            prefix = 'Page Parser ' + self._name + ': '
            
            e = HydrusExceptions.ParseException( prefix + str( e ) )
            
            raise e
            
        
        #
        
        whole_page_parse_results = []
        
        try:
            
            if 'post_index' not in parsing_context:
                
                parsing_context[ 'post_index' ] = '0'
                
            
            for content_parser in self._content_parsers:
                
                whole_page_parse_results.extend( content_parser.Parse( parsing_context, converted_parsing_text ) )
                
            
            if ParseResultsHavePursuableURLs( whole_page_parse_results ):
                
                parsing_context[ 'post_index' ] = str( int( parsing_context[ 'post_index' ] ) + 1 )
                
            
        except HydrusExceptions.ParseException as e:
            
            prefix = 'Page Parser ' + self._name + ': '
            
            e = HydrusExceptions.ParseException( prefix + str( e ) )
            
            raise e
            
        
        #
        
        all_parse_results = []
        
        if len( self._sub_page_parsers ) == 0:
            
            if len( whole_page_parse_results ) > 0:
                
                all_parse_results = [ whole_page_parse_results ]
                
            
        else:
            
            # we don't add the basic 'whole page' results to our results here since if we are using sub page parsers, that guy shouldn't have a URL in it; if there's no URL, we don't want it anyway!
            # he is however getting tacked onto every post parser by the sub page parsers
            
            sub_page_parsers = sorted( self._sub_page_parsers, key = lambda spp: spp.GetPageParser().GetName().casefold() )
            
            for sub_page_parser in sub_page_parsers:
                
                sub_page_parser_parse_results = sub_page_parser.Parse( whole_page_parse_results, parsing_context, converted_parsing_text )
                
                all_parse_results.extend( sub_page_parser_parse_results )
                
            
        
        return all_parse_results
        
    
    def ParsePretty( self, parsing_context, parsing_text ):
        
        try:
            
            all_parse_results = self.Parse( parsing_context, parsing_text )
            
            pretty_groups_of_parse_results = [ '\n'.join( [ ConvertParseResultToPrettyString( parse_result ) for parse_result in parse_results ] ) for parse_results in all_parse_results ]
            
            group_separator = '\n' * 2 + '*** SEPARATE FILE RESULTS BREAK ***' + '\n' * 2
            
            pretty_parse_result_text = group_separator.join( pretty_groups_of_parse_results )
            
        except HydrusExceptions.VetoException as e:
            
            all_parse_results = [ 1 ]
            
            pretty_parse_result_text = 'veto: ' + str( e )
            
        
        result_lines = []
        
        result_lines.append( '*** ' + HydrusNumbers.ToHumanInt( len( all_parse_results ) ) + ' RESULTS BEGIN ***' + '\n' )
        
        result_lines.append( pretty_parse_result_text )
        
        result_lines.append( '\n' + '*** RESULTS END ***' )
        
        results_text = '\n'.join( result_lines )
        
        return results_text
        
    
    def RegenerateParserKey( self ):
        
        self._parser_key = HydrusData.GenerateKey()
        
    
    def SetExampleURLs( self, example_urls ):
        
        self._example_urls = list( example_urls )
        
    
    def SetExampleParsingContext( self, example_parsing_context ):
        
        self._example_parsing_context = example_parsing_context
        
    
    def SetParserKey( self, parser_key ):
        
        self._parser_key = parser_key
        
    

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PAGE_PARSER ] = PageParser

class SubsidiaryPageParser( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_SUBSIDIARY_PAGE_PARSER
    SERIALISABLE_NAME = 'Subsidiary Page Parser'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, formula = None, page_parser = None ):
        
        if formula is None:
            
            formula = ParseFormulaHTML( tag_rules = [ ParseRuleHTML( rule_type = HTML_RULE_TYPE_DESCENDING, tag_name = 'div', tag_attributes = { 'class' : 'thumb' } ) ], content_to_fetch = HTML_CONTENT_HTML )
            
        
        if page_parser is None:
            
            page_parser = PageParser( 'new sub page parser' )
            
        
        self._formula = formula
        self._page_parser = page_parser
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_formula = self._formula.GetSerialisableTuple()
        serialisable_page_parser = self._page_parser.GetSerialisableTuple()
        
        return ( serialisable_formula, serialisable_page_parser )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_formula, serialisable_page_parser ) = serialisable_info
        
        self._formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula )
        self._page_parser = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_page_parser )
        
    
    def GetFormula( self ) -> ParseFormula:
        
        return self._formula
        
    
    def GetPageParser( self ) -> PageParser:
        
        return self._page_parser
        
    
    def Parse( self, parent_parse_results, parsing_context, parsing_text ):
        
        all_parse_results = []
        
        try:
            
            try:
                
                collapse_newlines = False
                
                posts = self._formula.Parse( parsing_context, parsing_text, collapse_newlines )
                
            except HydrusExceptions.ParseException:
                
                return all_parse_results
                
            
            for ( i, post ) in enumerate( posts ):
                
                try:
                    
                    page_parser_all_parse_results = self._page_parser.Parse( parsing_context, post )
                    
                except HydrusExceptions.VetoException:
                    
                    continue
                    
                
                for page_parser_parse_results in page_parser_all_parse_results:
                    
                    page_parser_parse_results.extend( parent_parse_results )
                    
                    all_parse_results.append( page_parser_parse_results )
                    
                
            
        except HydrusExceptions.ParseException as e:
            
            prefix = f'Subsidiary Page Parser {self._page_parser.GetName()}: '
            
            e = HydrusExceptions.ParseException( prefix + str( e ) )
            
            raise e
            
        
        return all_parse_results
        
    
    def SetFormula( self, formula: ParseFormula ):
        
        self._formula = formula
        
    
    def SetPageParser( self, page_parser: PageParser ):
        
        self._page_parser = page_parser
        
    

HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_SUBSIDIARY_PAGE_PARSER ] = SubsidiaryPageParser

class ParseNodeContentLink( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_NODE_CONTENT_LINK
    SERIALISABLE_NAME = 'Content Parsing Link'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, name = None, formula = None, children = None ):
        
        if name is None:
            
            name = ''
            
        
        if formula is None:
            
            formula = ParseFormulaHTML()
            
        
        if children is None:
            
            children = []
            
        
        self._name = name
        self._formula = formula
        self._children = children
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_formula = self._formula.GetSerialisableTuple()
        serialisable_children = [ child.GetSerialisableTuple() for child in self._children ]
        
        return ( self._name, serialisable_formula, serialisable_children )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._name, serialisable_formula, serialisable_children ) = serialisable_info
        
        self._formula = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_formula )
        self._children = [ HydrusSerialisable.CreateFromSerialisableTuple( serialisable_child ) for serialisable_child in serialisable_children ]
        
    
    def GetParsableContent( self ):
        
        children_parsable_content = set()
        
        for child in self._children:
            
            children_parsable_content.update( child.GetParsableContent() )
            
        
        return children_parsable_content
        
    
    def Parse( self, job_status, parsing_text, referral_url ):
        
        search_urls = self.ParseURLs( job_status, parsing_text, referral_url )
        
        content = []
        
        for search_url in search_urls:
            
            job_status.SetVariable( 'script_status', 'fetching ' + HydrusText.ElideText( search_url, 32 ) )
            
            network_job = ClientNetworkingJobs.NetworkJob( 'GET', search_url, referral_url = referral_url )
            
            network_job.OverrideBandwidth()
            
            CG.client_controller.network_engine.AddJob( network_job )
            
            try:
                
                network_job.WaitUntilDone()
                
            except HydrusExceptions.CancelledException:
                
                break
                
            except HydrusExceptions.NetworkException as e:
                
                if isinstance( e, HydrusExceptions.NotFoundException ):
                    
                    job_status.SetVariable( 'script_status', '404 - nothing found' )
                    
                    time.sleep( 2 )
                    
                    continue
                    
                elif isinstance( e, HydrusExceptions.NetworkException ):
                    
                    job_status.SetVariable( 'script_status', 'Network error! Details written to log.' )
                    
                    HydrusData.Print( 'Problem fetching ' + HydrusText.ElideText( search_url, 256 ) + ':' )
                    HydrusData.PrintException( e )
                    
                    time.sleep( 2 )
                    
                    continue
                    
                else:
                    
                    raise
                    
                
            
            linked_text = network_job.GetContentText()
            
            children_content = GetChildrenContent( job_status, self._children, linked_text, search_url )
            
            content.extend( children_content )
            
            if job_status.IsCancelled():
                
                raise HydrusExceptions.CancelledException( 'Job was cancelled.' )
                
            
        
        return content
        
    
    def ParseURLs( self, job_status, parsing_text, referral_url ):
        
        collapse_newlines = True
        
        basic_urls = self._formula.Parse( {}, parsing_text, collapse_newlines )
        
        absolute_urls = [ urllib.parse.urljoin( referral_url, basic_url ) for basic_url in basic_urls ]
        
        for url in absolute_urls:
            
            job_status.AddURL( url )
            
        
        return absolute_urls
        
    
    def ToPrettyStrings( self ):
        
        return ( self._name, 'link', ConvertParsableContentToPrettyString( self.GetParsableContent() ) )
        
    
    def ToTuple( self ):
        
        return ( self._name, self._formula, self._children )
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_NODE_CONTENT_LINK ] = ParseNodeContentLink

FILE_IDENTIFIER_TYPE_FILE = 0
FILE_IDENTIFIER_TYPE_MD5 = 1
FILE_IDENTIFIER_TYPE_SHA1 = 2
FILE_IDENTIFIER_TYPE_SHA256 = 3
FILE_IDENTIFIER_TYPE_SHA512 = 4
FILE_IDENTIFIER_TYPE_USER_INPUT = 5

file_identifier_string_lookup = {}

file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_FILE ] = 'the actual file (POST only)'
file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_MD5 ] = 'md5 hash'
file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_SHA1 ] = 'sha1 hash'
file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_SHA256 ] = 'sha256 hash'
file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_SHA512 ] = 'sha512 hash'
file_identifier_string_lookup[ FILE_IDENTIFIER_TYPE_USER_INPUT ] = 'custom user input'

# eventually transition this to be a flat 'generate page/gallery urls'
# the rest of the parsing system can pick those up automatically
# this nullifies the need for contentlink stuff, at least in its current borked form
class ParseRootFileLookup( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_PARSE_ROOT_FILE_LOOKUP
    SERIALISABLE_NAME = 'File Lookup Script'
    SERIALISABLE_VERSION = 2
    
    def __init__( self, name, url = None, query_type = None, file_identifier_type = None, file_identifier_string_converter = None, file_identifier_arg_name = None, static_args = None, children = None ):
        
        super().__init__( name )
        
        self._url = url
        self._query_type = query_type
        self._file_identifier_type = file_identifier_type
        self._file_identifier_string_converter = file_identifier_string_converter
        self._file_identifier_arg_name = file_identifier_arg_name
        self._static_args = static_args
        self._children = children
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_children = [ child.GetSerialisableTuple() for child in self._children ]
        serialisable_file_identifier_string_converter = self._file_identifier_string_converter.GetSerialisableTuple()
        
        return ( self._url, self._query_type, self._file_identifier_type, serialisable_file_identifier_string_converter, self._file_identifier_arg_name, self._static_args, serialisable_children )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._url, self._query_type, self._file_identifier_type, serialisable_file_identifier_string_converter, self._file_identifier_arg_name, self._static_args, serialisable_children ) = serialisable_info
        
        self._children = [ HydrusSerialisable.CreateFromSerialisableTuple( serialisable_child ) for serialisable_child in serialisable_children ]
        self._file_identifier_string_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_file_identifier_string_converter )
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( url, query_type, file_identifier_type, file_identifier_encoding, file_identifier_arg_name, static_args, serialisable_children ) = old_serialisable_info
            
            conversions = []
            
            if file_identifier_encoding == HC.ENCODING_RAW:
                
                pass
                
            elif file_identifier_encoding == HC.ENCODING_HEX:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_ENCODE, ClientStrings.ENCODING_TYPE_HEX_UTF8 ) )
                
            elif file_identifier_encoding == HC.ENCODING_BASE64:
                
                conversions.append( ( ClientStrings.STRING_CONVERSION_ENCODE, ClientStrings.ENCODING_TYPE_BASE64_UTF8 ) )
                
            
            file_identifier_string_converter = ClientStrings.StringConverter( conversions, 'some hash bytes' )
            
            serialisable_file_identifier_string_converter = file_identifier_string_converter.GetSerialisableTuple()
            
            new_serialisable_info = ( url, query_type, file_identifier_type, serialisable_file_identifier_string_converter, file_identifier_arg_name, static_args, serialisable_children )
            
            return ( 2, new_serialisable_info )
            
        
    
    def ConvertMediaToFileIdentifier( self, media ):
        
        if self._file_identifier_type == FILE_IDENTIFIER_TYPE_USER_INPUT:
            
            raise Exception( 'Cannot convert media to file identifier--this script takes user input!' )
            
        elif self._file_identifier_type == FILE_IDENTIFIER_TYPE_SHA256:
            
            return media.GetHash()
            
        elif self._file_identifier_type in ( FILE_IDENTIFIER_TYPE_MD5, FILE_IDENTIFIER_TYPE_SHA1, FILE_IDENTIFIER_TYPE_SHA512 ):
            
            sha256_hash = media.GetHash()
            
            if self._file_identifier_type == FILE_IDENTIFIER_TYPE_MD5:
                
                hash_type = 'md5'
                
            elif self._file_identifier_type == FILE_IDENTIFIER_TYPE_SHA1:
                
                hash_type = 'sha1'
                
            elif self._file_identifier_type == FILE_IDENTIFIER_TYPE_SHA512:
                
                hash_type = 'sha512'
                
            
            try:
                
                source_to_desired = CG.client_controller.Read( 'file_hashes', ( sha256_hash, ), 'sha256', hash_type )
                
                other_hash = list( source_to_desired.values() )[0]
                
                return other_hash
                
            except:
                
                raise Exception( 'I do not know that file\'s ' + hash_type + ' hash, so I cannot look it up!' )
                
            
        elif self._file_identifier_type == FILE_IDENTIFIER_TYPE_FILE:
            
            hash = media.GetHash()
            mime = media.GetMime()
            
            client_files_manager = CG.client_controller.client_files_manager
            
            try:
                
                path = client_files_manager.GetFilePath( hash, mime )
                
                return path
                
            except HydrusExceptions.FileMissingException as e:
                
                raise Exception( 'That file is not in the database\'s local files, so I cannot look it up!' )
                
            
        
    
    def FetchParsingText( self, job_status, file_identifier ):
        
        # add gauge report hook and in-stream cancel support to the get/post calls
        
        request_args = dict( self._static_args )
        
        if self._file_identifier_type != FILE_IDENTIFIER_TYPE_FILE:
            
            request_args[ self._file_identifier_arg_name ] = self._file_identifier_string_converter.Convert( file_identifier )
            
        
        f = None
        
        if self._query_type == HC.GET:
            
            if self._file_identifier_type == FILE_IDENTIFIER_TYPE_FILE:
                
                raise Exception( 'Cannot have a file as an argument on a GET query!' )
                
            
            single_value_parameters = []
            
            full_request_url = self._url + '?' + ClientNetworkingFunctions.ConvertQueryDictToText( request_args, single_value_parameters )
            
            job_status.SetVariable( 'script_status', 'fetching ' + HydrusText.ElideText( full_request_url, 32 ) )
            
            job_status.AddURL( full_request_url )
            
            network_job = ClientNetworkingJobs.NetworkJob( 'GET', full_request_url )
            
        elif self._query_type == HC.POST:
            
            additional_headers = {}
            files = None
            
            if self._file_identifier_type == FILE_IDENTIFIER_TYPE_FILE:
                
                job_status.SetVariable( 'script_status', 'uploading file' )
                
                path  = file_identifier
                
                if self._file_identifier_string_converter.MakesChanges():
                    
                    with open( path, 'rb' ) as f:
                        
                        file_bytes = f.read()
                        
                    
                    f_altered = self._file_identifier_string_converter.Convert( file_bytes )
                    
                    request_args[ self._file_identifier_arg_name ] = f_altered
                    
                    additional_headers[ 'content-type' ] = 'application/x-www-form-urlencoded'
                    
                else:
                    
                    f = open( path, 'rb' )
                    
                    files = { self._file_identifier_arg_name : f }
                    
                
            else:
                
                job_status.SetVariable( 'script_status', 'uploading identifier' )
                
                files = None
                
            
            network_job = ClientNetworkingJobs.NetworkJob( 'POST', self._url, body = request_args )
            
            if files is not None:
                
                network_job.SetFiles( files )
                
            
            for ( key, value ) in additional_headers.items():
                
                network_job.AddAdditionalHeader( key, value )
                
            
        
        # send nj to nj control on this panel here
        
        network_job.OverrideBandwidth()
        
        CG.client_controller.network_engine.AddJob( network_job )
        
        try:
            
            network_job.WaitUntilDone()
            
        except HydrusExceptions.NotFoundException:
            
            job_status.SetVariable( 'script_status', '404 - nothing found' )
            
            raise
            
        except HydrusExceptions.NetworkException as e:
            
            job_status.SetVariable( 'script_status', 'Network error!' )
            
            HydrusData.ShowException( e )
            
            raise
            
        finally:
            
            if f is not None:
                
                f.close()
                
            
        
        if job_status.IsCancelled():
            
            raise HydrusExceptions.CancelledException( 'Job was cancelled.' )
            
        
        parsing_text = network_job.GetContentText()
        
        return parsing_text
        
    
    def GetParsableContent( self ):
        
        children_parsable_content = set()
        
        for child in self._children:
            
            children_parsable_content.update( child.GetParsableContent() )
            
        
        return children_parsable_content
        
    
    def DoQuery( self, job_status, file_identifier ):
        
        try:
            
            try:
                
                parsing_text = self.FetchParsingText( job_status, file_identifier )
                
            except HydrusExceptions.NetworkException as e:
                
                return []
                
            
            parse_results = self.Parse( job_status, parsing_text )
            
            return parse_results
            
        except HydrusExceptions.CancelledException:
            
            job_status.SetVariable( 'script_status', 'Cancelled!' )
            
            return []
            
        finally:
            
            job_status.Finish()
            
        
    
    def UsesUserInput( self ):
        
        return self._file_identifier_type == FILE_IDENTIFIER_TYPE_USER_INPUT
        
    
    def Parse( self, job_status, parsing_text ):
        
        parse_results = GetChildrenContent( job_status, self._children, parsing_text, self._url )
        
        if len( parse_results ) == 0:
            
            job_status.SetVariable( 'script_status', 'Did not find anything.' )
            
        else:
            
            job_status.SetVariable( 'script_status', 'Found ' + HydrusNumbers.ToHumanInt( len( parse_results ) ) + ' rows.' )
            
        
        return parse_results
        
    
    def SetChildren( self, children ):
        
        self._children = children
        
    
    def ToPrettyStrings( self ):
        
        return ( self._name, HC.query_type_string_lookup[ self._query_type ], 'File Lookup', ConvertParsableContentToPrettyString( self.GetParsableContent() ) )
        
    
    def ToTuple( self ):
        
        return ( self._name, self._url, self._query_type, self._file_identifier_type, self._file_identifier_string_converter,  self._file_identifier_arg_name, self._static_args, self._children )
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_PARSE_ROOT_FILE_LOOKUP ] = ParseRootFileLookup
