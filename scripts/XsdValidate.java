import java.io.File;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;

/**
 * SAX-driven XSD validator. Unlike xmllint --schema, javax.xml.validation
 * validates a StreamSource incrementally instead of building a full DOM,
 * so peak memory stays roughly proportional to validation state (grammar +
 * key/unique tables) rather than to document size.
 *
 * Usage: java XsdValidate <schema.xsd> <file1.xml> [file2.xml ...]
 * Exits non-zero if any file fails to validate.
 */
public class XsdValidate {

    private static final class CollectingHandler implements ErrorHandler {
        final String file;
        boolean failed = false;

        CollectingHandler(String file) {
            this.file = file;
        }

        private String format(String level, SAXParseException e) {
            return String.format("%s:%d:%d: [%s] %s",
                    file, e.getLineNumber(), e.getColumnNumber(), level, e.getMessage());
        }

        @Override
        public void warning(SAXParseException e) {
            System.out.println(format("warning", e));
        }

        @Override
        public void error(SAXParseException e) {
            failed = true;
            System.out.println(format("error", e));
        }

        @Override
        public void fatalError(SAXParseException e) throws SAXException {
            failed = true;
            System.out.println(format("fatal", e));
            throw e;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: java XsdValidate <schema.xsd> <file1.xml> [file2.xml ...]");
            System.exit(2);
        }

        String schemaPath = args[0];
        List<String> xmlFiles = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            xmlFiles.add(args[i]);
        }

        SchemaFactory factory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        Schema schema = factory.newSchema(new File(schemaPath));

        boolean anyFailed = false;
        for (String xmlFile : xmlFiles) {
            System.out.println("== Validating " + xmlFile + " ==");
            Validator validator = schema.newValidator();
            CollectingHandler handler = new CollectingHandler(xmlFile);
            validator.setErrorHandler(handler);
            try {
                validator.validate(new StreamSource(new File(xmlFile)));
            } catch (SAXException e) {
                // fatalError already recorded and rethrown; nothing more to do.
            }
            if (handler.failed) {
                anyFailed = true;
            }
        }

        System.exit(anyFailed ? 1 : 0);
    }
}
